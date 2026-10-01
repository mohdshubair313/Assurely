"""Ingestion screening — untrusted-content check before the vector store.

Per AGENTS.md rule 3 (distributed guardrails) and LLD § 12:
  This is a SEPARATE guardrail from the Stage 4 compliance check.
  Acts as the single gate into the vector store: no document enters
  the vector store without an ADMIT screening result.

Screens scraped pages, uploaded files, and policy documents for:
  - Source domain allowlist (Tier 1 IRDAI / Tier 2 licensed insurers)
  - File type and size limits
  - PDF active content (JavaScript, launch actions, embedded files)
  - Hidden text (zero-width, bidi control characters, HTML comments)
  - Indirect prompt injection / instruction-like text aimed at a model
  - Long encoded payloads (base64, hex blobs)
  - Promotional or ranking language (AGENTS.md rule 1 violation)

Outcomes:
  - ADMIT: Document passes all checks; provenance recorded.
  - QUARANTINE: Document fails or screening errors (fail-closed);
    recorded in the review queue; never reaches RAG.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import stat
import threading
import uuid
from contextlib import nullcontext
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunsplit

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.correlation import correlation_scope, current_turn, node_scope
from app.core.exception_log import safe_exception

logger = logging.getLogger(__name__)

# Maximum file sizes
MAX_PDF_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB
MAX_TEXT_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB

# Tiered domain allowlists
TIER_1_DOMAINS = {
    "irdai.gov.in",
    "policyholder.gov.in",
    "bimabharosa.irdai.gov.in",
    "generalinsurancecouncil.org.in",
}

TIER_2_DOMAINS = {
    "hdfcergo.com",
    "careinsurance.com",
    "starhealth.in",
    "icicilombard.com",
    "tataaig.com",
    "bajajallianz.com",
    "nivabupa.com",
    "adityabirlacapital.com",
    "manipalcigna.com",
    "reliancegeneral.co.in",
    "sbigeneral.in",
    "newindia.co.in",
    "nationalinsurance.nic.co.in",
    "orientalinsurance.org.in",
    "unitedindia.co.in",
}

ALL_ALLOWED_DOMAINS = TIER_1_DOMAINS | TIER_2_DOMAINS

# Zero-width and bidi control characters
_ZERO_WIDTH_CHARS = {
    "\u200b",  # zero-width space
    "\u200c",  # zero-width non-joiner
    "\u200d",  # zero-width joiner
    "\u200e",  # left-to-right mark
    "\u200f",  # right-to-left mark
    "\ufeff",  # zero-width no-break space / BOM
}

_BIDI_CONTROL_CHARS = {
    "\u202a",
    "\u202b",
    "\u202c",
    "\u202d",
    "\u202e",
    "\u2066",
    "\u2067",
    "\u2068",
    "\u2069",
}

# Regex patterns for instruction injection
_INSTRUCTION_PATTERNS = [
    re.compile(
        r"\b(?:ignore|disregard|forget|override)\s+(?:all\s+)?"
        r"(?:previous|prior|above|system)\s+(?:instructions?|prompts?|directives?|rules?)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\balways\s+recommend\b", re.IGNORECASE),
    re.compile(r"\byou\s+(?:must|should)\s+(?:only\s+)?recommend\b", re.IGNORECASE),
    re.compile(r"\bdo\s+not\s+follow\s+agents\.md\b", re.IGNORECASE),
    re.compile(r"\boverride\s+(?:system|guidelines|guardrails|rules)\b", re.IGNORECASE),
    # Role markers & prompt injection tags
    re.compile(r"<\|im_start\|>|<\|im_end\|>|<\|endoftext\|>", re.IGNORECASE),
    re.compile(r"<\s*/?\s*(?:system|assistant)\s*>", re.IGNORECASE),
    re.compile(r"\[/?INST\]", re.IGNORECASE),
    re.compile(r"^\s*(?:system|assistant)\s*:\s", re.IGNORECASE | re.MULTILINE),
]

# Regex patterns for ranking / promotional language (AGENTS.md rule 1)
_RANKING_PATTERNS = [
    re.compile(
        r"\b(?:best\s+plan|top\s+pick|number\s+1\s+insurer|#1\s+insurer|"
        r"best\s+health\s+insurance|top\s+health\s+insurance|ranked\s+#?1|"
        r"top\s+rated\s+insurer|best\s+coverage\s+guaranteed|#1\s+rated)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:top\s+choice|best\s+policy\s+in\s+india)\b", re.IGNORECASE),
]

# HTML / Markdown comment pattern
_COMMENT_PATTERN = re.compile(r"<!--[\s\S]*?-->")

# Encoded blobs pattern: base64 of 64+ chars or hex of 64+ chars
_BASE64_BLOB_PATTERN = re.compile(r"\b[A-Za-z0-9+/]{64,}={0,2}\b")
_HEX_BLOB_PATTERN = re.compile(r"\b[0-9a-fA-F]{64,}\b")


class ScreeningOutcome(StrEnum):
    ADMIT = "admit"
    QUARANTINE = "quarantine"


class ScreeningResult(BaseModel):
    """Result of screening an incoming document before the vector store."""

    outcome: ScreeningOutcome
    reasons: list[str] = Field(default_factory=list)
    source_url: str
    version_hash: str
    timestamp: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    indexed_content_hash: str | None = None

    @property
    def is_admitted(self) -> bool:
        return self.outcome == ScreeningOutcome.ADMIT


class QuarantineRecord(BaseModel):
    """Audit log entry for a document failing ingestion screening."""

    record_id: str
    reason: str
    all_reasons: list[str]
    source_url: str
    version_hash: str
    timestamp: str
    document_snippet: str
    quarantined_by: str = "ingestion_screening"


def compute_sha256(content: str | bytes) -> str:
    """Compute the SHA-256 hex digest of the document content."""
    content_bytes = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(content_bytes).hexdigest()


def extract_document_text(content: str | bytes) -> str:
    """Return the exact UTF-8 text representation that screening/indexing use."""
    if isinstance(content, str):
        return content
    if content.startswith(b"%PDF-"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content), strict=True)
        extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
        if not extracted.strip():
            raise ValueError("PDF contains no extractable text")
        return extracted
    try:
        text = content.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("Unsupported binary document type") from exc
    if "\x00" in text:
        raise ValueError("Unsupported binary document type")
    return text


def check_domain_allowlist(source_url: str) -> list[str]:
    """Verify that source_url belongs to the IRDAI or licensed insurer allowlist."""
    if not source_url or not isinstance(source_url, str):
        return ["MISSING_SOURCE_URL: Document lacks a source URL"]

    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower().strip()
    if not hostname:
        return [f"INVALID_SOURCE_URL: Could not parse hostname from '{source_url}'"]

    # Check match against allowlist (exact or subdomain match)
    for allowed in ALL_ALLOWED_DOMAINS:
        if hostname == allowed or hostname.endswith(f".{allowed}"):
            return []

    return [
        f"DISALLOWED_DOMAIN: Host '{hostname}' is not on the Tier 1/2 "
        f"allowlist (IRDAI / licensed Indian insurers)"
    ]


def check_file_size_and_type(
    content: str | bytes, filename_or_mime: str = ""
) -> list[str]:
    """Check content size against maximum bounds."""
    content_len = len(content) if isinstance(content, bytes) else len(content.encode("utf-8"))
    is_pdf = isinstance(content, bytes) and content.startswith(b"%PDF-")

    if is_pdf:
        if content_len > MAX_PDF_SIZE_BYTES:
            return [
                f"FILE_TOO_LARGE: PDF size {content_len} bytes exceeds {MAX_PDF_SIZE_BYTES} bytes"
            ]
    else:
        if content_len > MAX_TEXT_SIZE_BYTES:
            return [
                f"FILE_TOO_LARGE: Text size {content_len} bytes exceeds {MAX_TEXT_SIZE_BYTES} bytes"
            ]
    return []


def check_pdf_active_content(content: str | bytes) -> list[str]:
    """Detect active / executable structures in PDF content."""
    if not isinstance(content, bytes) or not content.startswith(b"%PDF-"):
        return []

    violations: list[str] = []
    # Search for dangerous PDF action tags
    suspicious_tags = [
        (b"/JavaScript", "PDF JavaScript action (/JavaScript)"),
        (b"/JS", "PDF JavaScript tag (/JS)"),
        (b"/Launch", "PDF Launch action (/Launch)"),
        (b"/EmbeddedFiles", "PDF Embedded files (/EmbeddedFiles)"),
        (b"/RichMedia", "PDF RichMedia object (/RichMedia)"),
    ]
    for tag, desc in suspicious_tags:
        if tag in content:
            violations.append(f"PDF_ACTIVE_CONTENT: {desc} detected in PDF binary")

    return violations


def check_hidden_text_and_comments(text: str) -> list[str]:
    """Detect zero-width characters, bidi control anomalies, and comments."""
    violations: list[str] = []

    # Check zero-width characters
    zw_found = [char for char in text if char in _ZERO_WIDTH_CHARS]
    if zw_found:
        violations.append(
            f"HIDDEN_TEXT_ZERO_WIDTH: Found {len(zw_found)} zero-width characters in content"
        )

    # Check bidi control characters
    bidi_found = [char for char in text if char in _BIDI_CONTROL_CHARS]
    if bidi_found:
        violations.append(
            f"HIDDEN_TEXT_BIDI: Found {len(bidi_found)} bidirectional control characters"
        )

    # Check HTML / markdown comments
    comments = _COMMENT_PATTERN.findall(text)
    if comments:
        violations.append(
            f"HIDDEN_TEXT_COMMENT: Found {len(comments)} HTML/markdown comment blocks in content"
        )

    return violations


def check_instruction_text(text: str) -> list[str]:
    """Detect prompt injection and instruction-like language directed at an LLM."""
    violations: list[str] = []
    for pattern in _INSTRUCTION_PATTERNS:
        match = pattern.search(text)
        if match:
            violations.append(
                f"INSTRUCTION_INJECTION_DETECTED: Matched instruction pattern '{match.group(0)}'"
            )
    return violations


def check_encoded_blobs(text: str) -> list[str]:
    """Detect long base64 or hexadecimal payload blobs."""
    violations: list[str] = []

    b64_matches = _BASE64_BLOB_PATTERN.findall(text)
    if b64_matches:
        violations.append(
            f"ENCODED_PAYLOAD_DETECTED: Found {len(b64_matches)} long base64 blob(s)"
        )

    hex_matches = _HEX_BLOB_PATTERN.findall(text)
    if hex_matches:
        violations.append(
            f"ENCODED_PAYLOAD_DETECTED: Found {len(hex_matches)} long hexadecimal blob(s)"
        )

    return violations


def check_ranking_language(text: str) -> list[str]:
    """Detect promotional and ranking language under AGENTS.md rule 1."""
    violations: list[str] = []
    for pattern in _RANKING_PATTERNS:
        match = pattern.search(text)
        if match:
            violations.append(
                f"RANKING_LANGUAGE_DETECTED: Prohibited ranking/promotional phrasing "
                f"'{match.group(0)}' violates AGENTS.md rule 1"
            )
    return violations


def screen_document(
    content: str | bytes,
    source_url: str,
    metadata: dict[str, Any] | None = None,
) -> ScreeningResult:
    """Screen within the caller's correlation scope, creating one if absent.

    Request-scoped ingestion reuses its session/trace IDs and profile snapshot.
    Background or direct screening gets its own trace ID. Document text and
    source URL are added only temporarily as scrub context and then discarded.
    """
    active_turn = current_turn.get()
    scope = nullcontext(active_turn) if active_turn is not None else correlation_scope()
    with scope as turn, node_scope("ingestion-screening"):
        previous_profile = turn.profile_snapshot
        scrub_context = dict(previous_profile or {})
        if isinstance(content, bytes):
            scrub_context["screening_document"] = content.decode("utf-8", errors="replace")
        else:
            scrub_context["screening_document"] = content
        scrub_context["screening_source_url"] = source_url
        turn.profile_snapshot = scrub_context
        try:
            return _screen_document_impl(content, source_url, metadata)
        finally:
            turn.profile_snapshot = previous_profile


def _screen_document_impl(
    content: str | bytes,
    source_url: str,
    metadata: dict[str, Any] | None = None,
) -> ScreeningResult:
    """Screen an incoming document across all deterministic security checks.

    Fail-closed: any unhandled exception automatically results in QUARANTINE.
    """
    version_hash = compute_sha256(content)
    now_iso = datetime.now(UTC).isoformat()
    meta = dict(metadata or {})

    reasons: list[str] = []
    text_content = ""

    try:
        # 1. Source domain allowlist check
        reasons.extend(check_domain_allowlist(source_url))

        # 2. File size and type check
        reasons.extend(check_file_size_and_type(content))

        # 3. PDF active content check (if binary PDF)
        reasons.extend(check_pdf_active_content(content))

        # Extract the exact representation sent to the vector store. Screening
        # the original bytes alone misses compressed or encoded PDF text.
        try:
            text_content = extract_document_text(content)
        except Exception:
            text_content = ""
            if isinstance(content, bytes) and content.startswith(b"%PDF-"):
                reasons.append("PDF_TEXT_EXTRACTION_FAILED: No safe text could be extracted")
            else:
                reasons.append("UNSUPPORTED_FILE_TYPE: Document is not supported UTF-8 text or PDF")

        if text_content:
            # 4. Hidden text, bidi controls, and comment blocks
            reasons.extend(check_hidden_text_and_comments(text_content))

            # 5. Model instruction injection
            reasons.extend(check_instruction_text(text_content))

            # 6. Encoded blobs (base64 / hex)
            reasons.extend(check_encoded_blobs(text_content))

            # 7. Promotional / ranking language
            reasons.extend(check_ranking_language(text_content))

    except Exception as exc:
        error_record = safe_exception(exc)
        logger.error(
            "Unexpected error during ingestion screening: "
            "exception_class=%s message=%s",
            error_record["exception_class"],
            error_record["message"],
        )
        reasons.append(
            "SCREENING_ERROR: Screening execution failed unexpectedly "
            f"(exception_class={error_record['exception_class']})"
        )

    if reasons:
        outcome = ScreeningOutcome.QUARANTINE
        logger.warning(
            "Document quarantined (hash=%s, source=%s, reasons=%s)",
            version_hash[:12],
            source_url,
            reasons,
        )
    else:
        outcome = ScreeningOutcome.ADMIT
        logger.info(
            "Document admitted (hash=%s, source=%s)",
            version_hash[:12],
            source_url,
        )

    return ScreeningResult(
        outcome=outcome,
        reasons=reasons,
        source_url=source_url,
        version_hash=version_hash,
        timestamp=now_iso,
        metadata=meta,
        indexed_content_hash=(compute_sha256(text_content) if text_content else None),
    )


class QuarantineStore:
    """Private, restartable review queue for quarantined document metadata."""

    def __init__(self, log_path: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._records: list[QuarantineRecord] = []
        if log_path is None:
            settings = get_settings()
            log_dir = Path(settings.exception_log_dir).parent / "quarantine"
            self.log_path = log_dir / "quarantine_records.jsonl"
        else:
            self.log_path = log_path
        self.log_path = self.log_path.absolute()
        self._secure_storage()
        self._load_records()

    def _secure_storage(self) -> None:
        """Create the queue with owner-only POSIX permissions and reject links."""
        if os.name != "posix":
            raise RuntimeError(
                "Restricted quarantine storage requires POSIX permissions; use Docker"
            )
        if self.log_path.resolve(strict=False) != self.log_path:
            raise RuntimeError("Quarantine path must not contain symlinks")
        self.log_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        parent = self.log_path.parent
        parent_info = parent.stat()
        if parent_info.st_uid != os.geteuid() or not stat.S_ISDIR(parent_info.st_mode):
            raise RuntimeError("Quarantine directory must belong to the service account")
        parent.chmod(0o700)
        flags = os.O_CREAT | os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.log_path, flags, 0o600)
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or info.st_nlink != 1
            ):
                raise RuntimeError(
                    "Quarantine file must be a regular file owned by the service account"
                )
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)

    def _load_records(self) -> None:
        """Restore persisted review records on process startup; fail on corruption."""
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.log_path, flags)
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    record = QuarantineRecord.model_validate_json(line)
                except Exception as exc:
                    raise RuntimeError(
                        f"Quarantine record file is invalid at line {line_number}"
                    ) from exc
                self._records.append(record)

    @staticmethod
    def _safe_source_url(source_url: str) -> str:
        """Drop credentials, query strings, and fragments before persistence."""
        try:
            parsed = urlparse(source_url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                return "[SOURCE REDACTED]"
            host = parsed.hostname
            if ":" in host:
                host = f"[{host}]"
            try:
                if parsed.port is not None:
                    host = f"{host}:{parsed.port}"
            except ValueError:
                return "[SOURCE REDACTED]"
            return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
        except Exception:
            return "[SOURCE REDACTED]"

    @staticmethod
    def _reason_codes(reasons: list[str]) -> list[str]:
        """Persist stable screening categories, never matched source text."""
        codes = [reason.partition(":")[0].strip()[:80] for reason in reasons]
        return list(dict.fromkeys(code or "SCREENING_ERROR" for code in codes))

    def add_quarantine(
        self,
        screening_result: ScreeningResult,
        content: str | bytes,
    ) -> QuarantineRecord:
        """Add a quarantined document result to the in-memory queue and persistent log."""
        reason_codes = self._reason_codes(screening_result.reasons)

        record = QuarantineRecord(
            record_id=str(uuid.uuid4()),
            reason=reason_codes[0] if reason_codes else "SCREENING_ERROR",
            all_reasons=reason_codes,
            source_url=self._safe_source_url(screening_result.source_url),
            version_hash=screening_result.version_hash,
            timestamp=screening_result.timestamp,
            document_snippet="[DOCUMENT CONTENT REDACTED]",
        )

        with self._lock:
            self._secure_storage()
            flags = os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(self.log_path, flags)
            try:
                info = os.fstat(fd)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.geteuid()
                    or info.st_nlink != 1
                ):
                    raise RuntimeError("Unsafe quarantine record file")
                os.fchmod(fd, 0o600)
                payload = (
                    json.dumps(record.model_dump(), ensure_ascii=False) + "\n"
                ).encode("utf-8")
                remaining = memoryview(payload)
                while remaining:
                    written = os.write(fd, remaining)
                    remaining = remaining[written:]
                os.fsync(fd)
            finally:
                os.close(fd)
            self._records.append(record)

        return record

    def list_records(self) -> list[QuarantineRecord]:
        with self._lock:
            return list(self._records)

    def get_by_hash(self, version_hash: str) -> QuarantineRecord | None:
        with self._lock:
            for rec in self._records:
                if rec.version_hash == version_hash:
                    return rec
            return None

    def clear(self) -> None:
        """Clear the in-memory records (used in testing)."""
        with self._lock:
            self._records.clear()


# Global singleton quarantine store
_quarantine_store: QuarantineStore | None = None


def get_quarantine_store() -> QuarantineStore:
    global _quarantine_store
    if _quarantine_store is None:
        _quarantine_store = QuarantineStore()
    return _quarantine_store
