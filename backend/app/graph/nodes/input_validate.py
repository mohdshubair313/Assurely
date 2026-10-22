"""Validate and sanitize each user turn before any model-backed graph node."""

from __future__ import annotations

import re
from typing import Any

from app.graph.state import SessionState
from app.guardrails.input_validation import REJECTION_KEY, prepare_messages

_HINGLISH_MARKERS = re.compile(r"\b(kya|hai|nahi|mujhe|mera|meri|aap|kaise|chahiye)\b", re.I)


def _detect_language(text: str) -> str:
    """Detect supported output language from script and common Hinglish markers."""
    devanagari = sum("\u0900" <= char <= "\u097f" for char in text)
    latin = sum(char.isascii() and char.isalpha() for char in text)
    if devanagari and latin:
        return "hi-en-mixed"
    if devanagari:
        return "hi"
    if _HINGLISH_MARKERS.search(text):
        return "hi-en-mixed"
    return "en"


async def input_validate_node(state: SessionState) -> dict[str, Any]:
    """Fail closed on malformed/hostile turns and scrub user text before use."""
    sanitized = prepare_messages(state.get("messages", []))
    latest = sanitized[-1]
    code = latest.get(REJECTION_KEY)
    updates: dict[str, Any] = {
        "messages": sanitized,
        "input_status": "rejected" if code else "accepted",
        "input_rejection_code": code,
        "approved": False,
        "delivery_hold": True,
    }
    if code:
        return updates
    language = state.get("target_language")
    if language not in {"en", "hi", "hi-en-mixed"}:
        language = _detect_language(latest["content"])
    updates["target_language"] = language
    return updates
