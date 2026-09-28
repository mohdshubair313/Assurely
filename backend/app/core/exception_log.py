"""Restricted exception records and a content-free general logging boundary.

Only structural diagnostic data is serialized. Exception strings, traceback
source lines, locals, notes and logging arguments are never formatted. The
Linux service account owns a 0700 directory and 0600 records; reading through
the CLI requires the OS administrator role. Native Windows must use Docker.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import stat
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from app.core.config import Settings
from app.core.correlation import current_node, current_turn

# ── Identifier and record-name validation ────────────────────────────────────
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,159}$")
_RECORD_NAME = re.compile(r"^[0-9a-f]{32}\.json$")


def _identifier(value: str) -> str:
    return value if _IDENTIFIER.fullmatch(value) else "redacted"


# Exception classes whose messages are safe to keep verbatim.
# These contain operational/infrastructure diagnostics, not user data.
ALLOWLISTED_EXCEPTION_CLASSES: frozenset[str] = frozenset({
    # Database connectivity
    "ConnectionRefusedError",
    "ConnectionResetError",
    "ConnectionAbortedError",
    "ConnectionError",
    "OperationalError",
    "InterfaceError",
    "DisconnectionError",
    # HTTP/network
    "TimeoutError",
    "ConnectTimeout",
    "ReadTimeout",
    "HTTPStatusError",
    "ConnectError",
    "RemoteProtocolError",
    # Provider status codes
    "RateLimitError",
    "APIStatusError",
    "ServiceUnavailableError",
    "InternalServerError",
    "AuthenticationError",
    # Redis
    "RedisConnectionError",
    "RedisTimeoutError",
    "ResponseError",
    # General infrastructure
    "OSError",
    "FileNotFoundError",
    "PermissionError",
    "IsADirectoryError",
})

# PII patterns to scrub from non-allowlisted exception messages.
_PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Indian phone numbers (+91 / 0-prefixed / bare 10-digit)
    (re.compile(r"(?:\+91[\s-]?|0)?[6-9]\d{9}"), "[PHONE]"),
    # Email addresses
    (re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"), "[EMAIL]"),
    # Aadhaar numbers (12 digits, optionally space/dash separated in groups of 4)
    (re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"), "[AADHAAR]"),
    # PAN card (ABCDE1234F format)
    (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), "[PAN]"),
    # Indian PIN codes (6 digits starting with 1-9)
    (re.compile(r"\b[1-9]\d{5}\b"), "[PIN]"),
    # Date of birth patterns (DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD)
    (re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"), "[DATE]"),
    # INR amounts with commas (₹1,50,000 or Rs. 1,50,000)
    (re.compile(r"(?:₹|Rs\.?\s*)\d[\d,]+"), "[AMOUNT]"),
]


def _scrub_profile_values(message: str, profile_values: frozenset[str]) -> str:
    """Remove known profile field values from a message."""
    for value in profile_values:
        if value and len(value) >= 2:
            message = message.replace(value, "[PROFILE]")
    return message


def _scrub_pii(message: str) -> str:
    """Apply PII regex patterns to scrub known sensitive formats."""
    for pattern, replacement in _PII_PATTERNS:
        message = pattern.sub(replacement, message)
    return message


# HTTP/network exception classes where URL query strings must be stripped.
_HTTP_EXCEPTION_CLASSES: frozenset[str] = frozenset({
    "HTTPStatusError",
    "RequestError",
    "ConnectError",
    "ReadTimeout",
    "ConnectTimeout",
    "TimeoutException",
    "HTTPError",
    "RemoteProtocolError",
    "InvalidURL",
    "UnsupportedProtocol",
})

_HTTP_URL_WITH_QUERY = re.compile(r"(https?://[^\s?\"'<>)]+)\?[^\s\"'<>)]*")
_PARAM_PATTERN = re.compile(
    r"(?i)(?:[?&]|\b)(key|api_key|apikey|token|access_token|secret|password|auth|client_secret)=([^\s&\"'<>)]+)"
)


def _strip_url_query_strings(message: str) -> str:
    """Strip ?query_string from HTTP/HTTPS URLs in error messages."""
    return _HTTP_URL_WITH_QUERY.sub(r"\1", message)


def _scrub_param_match(m: re.Match[str]) -> str:
    """Preserve leading delimiter (? or & or word boundary) while redacting value."""
    full = m.group(0)
    key = m.group(1)
    prefix = full[: full.lower().find(key.lower())]
    return f"{prefix}{key}=[REDACTED]"


def scrub_secrets(message: str) -> str:
    """Scrub credentials, tokens, API keys, and sensitive parameters from any message.

    Applied to ALL exception messages, allowlisted infrastructure errors included.
    """
    # 1. Credentials in connection URLs (e.g., postgresql://user:pass@host)
    message = re.sub(
        r"(?i)([a-z0-9+.-]+://[^/:]+:)([^@]+)(@)",
        r"\g<1>[REDACTED]\3",
        message,
    )
    # 2. Bearer tokens
    message = re.sub(r"(?i)\bbearer\s+[a-z0-9._~+/-]+=*", "Bearer [REDACTED]", message)
    # 3. Authorization header
    message = re.sub(r"(?i)\bauthorization\s*:\s*[^\s,;]+", "Authorization: [REDACTED]", message)
    # 4. Sensitive parameter assignments (key=..., token=..., etc.)
    message = _PARAM_PATTERN.sub(_scrub_param_match, message)
    # 5. Known API key prefixes (Groq, OpenAI, Google Gemini)
    message = re.sub(r"\b(?:gsk_|sk-|AIza)[A-Za-z0-9_\-]{16,}\b", "[API_KEY]", message)
    return message


def scrub_message(
    message: str,
    profile_values: frozenset[str] | None = None,
) -> str:
    """Scrub PII from an exception message.

    First removes known profile values (exact substring match),
    then applies PII regex patterns.
    """
    if profile_values:
        message = _scrub_profile_values(message, profile_values)
    message = _scrub_pii(message)
    return message


def _get_profile_values() -> frozenset[str]:
    """Extract known profile values from the current graph state for scrubbing."""
    turn = current_turn.get()
    if turn is None:
        return frozenset()
    values: set[str] = set()
    # Turn may carry a profile snapshot for scrubbing context.
    profile = getattr(turn, "profile_snapshot", None)
    if isinstance(profile, dict):
        for key in ("name", "city", "phone", "email", "aadhaar", "pan"):
            val = profile.get(key)
            if isinstance(val, str) and val.strip():
                values.add(val.strip())
        # Also scrub numeric profile values as strings
        for key in ("age", "dependents"):
            val = profile.get(key)
            if val is not None:
                values.add(str(val))
    return frozenset(values)


def safe_exception(exc: BaseException) -> dict[str, Any]:
    """Retain class, stack locations, and conditionally scrubbed messages.

    Secrets, credentials, and URL query strings are scrubbed from EVERY message,
    including allowlisted infrastructure exception classes. Allowlisted classes
    keep their non-secret diagnostic text intact. Non-allowlisted classes get
    additional PII and profile-value scrubbing.
    """
    profile_values = _get_profile_values()
    chain: list[dict[str, Any]] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen and len(chain) < 8:
        seen.add(id(current))
        frames: list[dict[str, str | int]] = []
        tb = current.__traceback__
        while tb is not None and len(frames) < 64:
            code = tb.tb_frame.f_code
            # Basename only: absolute paths can contain personal directory names.
            frames.append({
                "file": _identifier(Path(code.co_filename).name),
                "function": _identifier(code.co_name),
                "line": tb.tb_lineno,
            })
            tb = tb.tb_next

        class_name = type(current).__name__
        safe_class = _identifier(class_name)

        raw = str(current)
        # Strip query strings from URLs in httpx / HTTP errors.
        if (
            class_name in _HTTP_EXCEPTION_CLASSES
            or hasattr(current, "request")
            or hasattr(current, "response")
        ):
            raw = _strip_url_query_strings(raw)

        # Apply secret scrubber to every message, allowlisted ones included.
        raw = scrub_secrets(raw)

        if class_name in ALLOWLISTED_EXCEPTION_CLASSES:
            # Infrastructure errors: keep message for debugging (secrets already scrubbed).
            message = raw
        else:
            # Scrub PII and known profile values; keep the structural info.
            message = scrub_message(raw, profile_values)

        chain.append({
            "exception_class": safe_class,
            "message": message,
            "traceback": frames,
        })
        current = current.__cause__ or (
            None if current.__suppress_context__ else current.__context__
        )
    return {**chain[0], "causes": chain[1:]}


class RestrictedExceptionHandler(logging.Handler):
    """One bounded JSON record per exception, outside stdout/container logs."""

    def __init__(self, directory: str, retention_hours: int, max_records: int) -> None:
        super().__init__()
        if os.name != "posix":
            raise RuntimeError("Restricted logging requires POSIX permissions; use Docker")
        self.directory = Path(directory).absolute()
        if self.directory.resolve() != self.directory:
            raise RuntimeError("Exception directory must not contain symlinks")
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.directory.stat().st_uid != os.geteuid():
            raise RuntimeError("Exception directory must belong to the service account")
        self.directory.chmod(0o700)
        self.retention_seconds = retention_hours * 3600
        self.max_records = max_records
        self.failed = False
        # Fail startup if writes or retention cannot be enforced.
        probe = self.directory / (uuid.uuid4().hex + ".probe")
        fd = os.open(probe, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        probe.unlink()
        self.prune()

    def prune(self) -> None:
        """Apply an age limit even while idle, plus a bounded record count."""
        assert self.lock is not None
        with self.lock:
            cutoff = time.time() - self.retention_seconds
            retained: list[tuple[float, Path]] = []
            for path in self.directory.iterdir():
                if not _RECORD_NAME.fullmatch(path.name):
                    continue
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
                    raise RuntimeError("Unsafe exception record permissions")
                path.chmod(0o600)
                if info.st_mtime <= cutoff:
                    path.unlink()
                else:
                    retained.append((info.st_mtime, path))
            for _, path in sorted(retained)[:max(0, len(retained) - self.max_records)]:
                path.unlink()

    def emit(self, record: logging.LogRecord) -> None:
        # This handler receives only already-sanitized records from PrivacyFilter.
        payload: dict[str, Any] = record.__dict__["restricted_payload"]
        path = self.directory / (payload["error_ref"] + ".json")
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        self.prune()


class PrivacyFilter(logging.Filter):
    """Never allow original log messages or exception text onto general logs."""

    def __init__(self, sink: RestrictedExceptionHandler) -> None:
        super().__init__()
        self.sink = sink

    def filter(self, record: logging.LogRecord) -> bool:
        exc = record.exc_info[1] if record.exc_info else None
        # Older recovery paths log warnings from except blocks without exc_info.
        if exc is None and record.name.startswith("app."):
            exc = sys.exc_info()[1]
        if exc is not None:
            turn = current_turn.get()
            error_ref = next(
                (ref for error, ref, _ in turn.errors if error is exc), None
            ) if turn else None
            if error_ref is None:
                error_ref = uuid.uuid4().hex
                if turn:
                    turn.errors.append((exc, error_ref, current_node.get()))
                payload = {
                    "error_ref": error_ref,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "node": _identifier(current_node.get()),
                    "session_id": None,
                    "trace_id": None,
                    "decision_trace_id": None,
                    **(turn.identifiers() if turn else {}),
                    **safe_exception(exc),
                }
                private_record = logging.makeLogRecord({"restricted_payload": payload})
                try:
                    self.sink.handle(private_record)
                except Exception:
                    # Never invoke logging.handleError: it prints original content.
                    self.sink.failed = True
            record.msg = f"error_ref={error_ref}"
        else:
            # Existing INFO logs include profiles and queries. Keep only code location.
            record.msg = (
                f"event={_identifier(record.name)}:{_identifier(record.funcName)}:{record.lineno}"
            )
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


class SafeStreamHandler(logging.StreamHandler[TextIO]):
    def handleError(self, record: logging.LogRecord) -> None:  # noqa: N802 - stdlib override
        """A failed stream must never make logging print the original record."""


class LoggingBoundary:
    """Install once per app lifespan and restore host/test logging on shutdown."""

    def __init__(self, settings: Settings, stream: TextIO | None = None) -> None:
        self.sink = RestrictedExceptionHandler(
            settings.exception_log_dir,
            settings.exception_log_retention_hours,
            settings.exception_log_max_records,
        )
        self.handler = SafeStreamHandler(stream)
        self.handler.addFilter(PrivacyFilter(self.sink))
        self.handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        self.saved: list[tuple[logging.Logger, list[logging.Handler], bool, int]] = []
        # Cover Uvicorn and third-party handlers as well as app loggers. Future
        # ordinary loggers propagate to root. Deployment must not add raw handlers.
        loggers = [logging.getLogger()] + [
            item for item in logging.Logger.manager.loggerDict.values()
            if isinstance(item, logging.Logger)
        ]
        for logger in loggers:
            self.saved.append((logger, logger.handlers[:], logger.propagate, logger.level))
            logger.handlers = []
            logger.propagate = True
        root = logging.getLogger()
        root.handlers = [self.handler]
        root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    def close(self) -> None:
        for logger, handlers, propagate, level in self.saved:
            logger.handlers = handlers
            logger.propagate = propagate
            logger.setLevel(level)
        self.handler.close()
        self.sink.close()


def admin_read(directory: str, error_ref: str) -> dict[str, Any]:
    """Local OS-admin read path; there is deliberately no public HTTP endpoint."""
    if os.name != "posix" or os.geteuid() != 0:
        raise PermissionError("OS administrator role required")
    if not re.fullmatch(r"[0-9a-f]{32}", error_ref):
        raise ValueError("Invalid error reference")
    path = Path(directory) / f"{error_ref}.json"
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, encoding="utf-8") as stream:
        return dict(json.load(stream))


if __name__ == "__main__":
    from app.core.config import get_settings

    parser = argparse.ArgumentParser(description="OS-admin restricted exception reader")
    parser.add_argument("error_ref")
    args = parser.parse_args()
    print(json.dumps(admin_read(get_settings().exception_log_dir, args.error_ref), indent=2))
