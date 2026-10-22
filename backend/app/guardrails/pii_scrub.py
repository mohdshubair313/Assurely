"""Conservative PII masking for untrusted chat text before model calls."""

from __future__ import annotations

import re

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"), "[EMAIL]"),
    (re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b"), "[AADHAAR]"),
    (re.compile(r"(?i)\b[A-Z]{5}\d{4}[A-Z]\b"), "[PAN]"),
    (re.compile(r"(?i)\b[A-Z]{4}0[A-Z0-9]{6}\b"), "[IFSC]"),
    (re.compile(r"(?<!\d)(?:\+?91[ -]?)?[6-9]\d{9}(?!\d)"), "[PHONE]"),
)


def scrub_pii(text: str) -> str:
    """Mask identifiers without logging values or expanding the message length."""
    for pattern, replacement in _PATTERNS:
        def mask(match: re.Match[str], label: str = replacement) -> str:
            return label if len(label) <= len(match.group()) else "[PII]"

        text = pattern.sub(mask, text)
    return text
