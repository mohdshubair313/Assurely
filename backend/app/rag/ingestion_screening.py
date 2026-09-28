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
import json
import logging
import re
import threading
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app.core.config import get_settings

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
    """Screen an incoming document across all deterministic security checks.

    Fail-closed: any unhandled exception automatically results in QUARANTINE.
    """
    version_hash = compute_sha256(content)
    now_iso = datetime.now(UTC).isoformat()
    meta = dict(metadata or {})

    reasons: list[str] = []

    try:
        # 1. Source domain allowlist check
        reasons.extend(check_domain_allowlist(source_url))

        # 2. File size and type check
        reasons.extend(check_file_size_and_type(content))

        # 3. PDF active content check (if binary PDF)
        reasons.extend(check_pdf_active_content(content))

        # Extract text representation for text-based checks
        if isinstance(content, bytes):
            try:
                text_content = content.decode("utf-8", errors="replace")
            except Exception:
                text_content = ""
        else:
            text_content = content

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
        logger.exception("Unexpected error during ingestion screening: %s", exc)
        reasons.append(f"SCREENING_ERROR: Screening execution failed unexpectedly ({exc})")

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
    )


class QuarantineStore:
    """Thread-safe review queue for quarantined documents."""

    def __init__(self, log_path: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._records: list[QuarantineRecord] = []
        if log_path is None:
            settings = get_settings()
            log_dir = Path(settings.exception_log_dir).parent / "quarantine"
            self.log_path = log_dir / "quarantine_records.jsonl"
        else:
            self.log_path = log_path

    def add_quarantine(
        self,
        screening_result: ScreeningResult,
        content: str | bytes,
    ) -> QuarantineRecord:
        """Add a quarantined document result to the in-memory queue and persistent log."""
        if isinstance(content, bytes):
            snippet = content[:200].decode("utf-8", errors="replace")
        else:
            snippet = content[:200]

        record = QuarantineRecord(
            record_id=str(uuid.uuid4()),
            reason=screening_result.reasons[0] if screening_result.reasons else "Unknown",
            all_reasons=screening_result.reasons,
            source_url=screening_result.source_url,
            version_hash=screening_result.version_hash,
            timestamp=screening_result.timestamp,
            document_snippet=snippet,
        )

        with self._lock:
            self._records.append(record)
            try:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record.model_dump(), ensure_ascii=False) + "\n")
            except Exception as e:
                logger.error("Failed to write quarantine record to %s: %s", self.log_path, e)

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
