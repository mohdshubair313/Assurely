"""Validate and sanitize each user turn before any model-backed graph node."""

from __future__ import annotations

import re
from typing import Any

from app.graph.state import SessionState
from app.guardrails.injection_screen import contains_prompt_injection
from app.guardrails.pii_scrub import scrub_pii

MAX_MESSAGE_CHARS = 4000
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
    messages = list(state.get("messages", []))
    user_indices = [i for i, msg in enumerate(messages) if msg.get("role") == "user"]
    if not user_indices:
        return {"input_status": "rejected", "input_rejection_code": "missing_user_message"}

    latest = messages[user_indices[-1]].get("content")
    sanitized = [
        {**msg, "content": scrub_pii(msg["content"])}
        if msg.get("role") == "user" and isinstance(msg.get("content"), str)
        else msg
        for msg in messages
    ]
    if not isinstance(latest, str) or not latest.strip():
        return {
            "messages": sanitized,
            "input_status": "rejected",
            "input_rejection_code": "empty_message",
        }
    if len(latest) > MAX_MESSAGE_CHARS:
        return {
            "messages": sanitized,
            "input_status": "rejected",
            "input_rejection_code": "message_too_long",
        }
    if contains_prompt_injection(latest):
        return {
            "messages": sanitized,
            "input_status": "rejected",
            "input_rejection_code": "unsafe_directive",
        }
    language = state.get("target_language")
    if language not in {"en", "hi", "hi-en-mixed"}:
        language = _detect_language(latest)
    return {
        "messages": sanitized,
        "input_status": "accepted",
        "input_rejection_code": None,
        "target_language": language,
    }
