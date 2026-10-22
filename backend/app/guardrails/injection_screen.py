"""Deterministic screening for common direct prompt-injection directives."""

from __future__ import annotations

import re
import unicodedata

_DIRECTIVE_PATTERNS = (
    re.compile(
        r"\bignore\b.{0,50}\b(previous|prior|above|system|developer)\b"
        r".{0,30}\b(instructions?|prompts?)\b",
        re.I,
    ),
    re.compile(
        r"\b(reveal|print|show|repeat|expose)\b.{0,40}\b(system|developer)\s+"
        r"(prompt|message|instructions?)\b",
        re.I,
    ),
    re.compile(
        r"\b(you are now|act as|pretend to be)\b.{0,50}\b"
        r"(unrestricted|jailbreak|DAN|system|developer)\b",
        re.I,
    ),
    re.compile(
        r"\b(disable|bypass|override)\b.{0,30}\b"
        r"(safety|guardrails?|policy|restrictions?)\b",
        re.I,
    ),
)


def contains_prompt_injection(text: str) -> bool:
    """Return true for common directive-shaped override attempts.

    This is a narrow deterministic screen, not a claim that all hostile content
    can be detected. Policy-document ingestion screening remains separate.
    """
    # Normalize for screening only; preserve legitimate user wording for intake.
    normalized = unicodedata.normalize("NFKC", text)
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Cf")
    normalized = " ".join(normalized.split())
    return any(pattern.search(normalized) is not None for pattern in _DIRECTIVE_PATTERNS)
