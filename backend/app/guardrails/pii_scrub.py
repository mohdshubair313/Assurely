"""Conservative PII masking for untrusted chat text before model calls."""

from __future__ import annotations

import re

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"), "[EMAIL REDACTED]"),
    (re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b"), "[AADHAAR REDACTED]"),
    (re.compile(r"(?i)\b[A-Z]{5}\d{4}[A-Z]\b"), "[PAN REDACTED]"),
    (re.compile(r"(?i)\b[A-Z]{4}0[A-Z0-9]{6}\b"), "[IFSC REDACTED]"),
    (re.compile(r"(?<!\d)(?:\+?91[ -]?)?[6-9]\d{9}(?!\d)"), "[PHONE REDACTED]"),
)


def scrub_pii(text: str) -> str:
    """Mask common Indian identifiers and contact details without logging values."""
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text
