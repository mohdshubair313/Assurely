"""Shared boundary screening before checkpointing and before model-backed nodes."""

from __future__ import annotations

from typing import Any

from app.guardrails.injection_screen import contains_prompt_injection
from app.guardrails.pii_scrub import scrub_pii

MAX_MESSAGE_CHARS = 4000
REJECTED_MESSAGE = "[Message withheld by input validation.]"
REJECTION_KEY = "input_rejection_code"
_REJECTION_CODES = frozenset({
    "missing_user_message", "malformed_messages", "empty_message",
    "message_too_long", "unsafe_directive",
})


def rejected_message(code: str) -> dict[str, Any]:
    """Keep session continuity and audit classification without rejected content."""
    return {"role": "user", "content": REJECTED_MESSAGE, REJECTION_KEY: code}


def prepare_user_message(content: object) -> dict[str, Any]:
    """Check original bounds before masking; retain no rejected payload."""
    if not isinstance(content, str) or not content.strip():
        return rejected_message("empty_message")
    if len(content) > MAX_MESSAGE_CHARS:
        return rejected_message("message_too_long")
    if contains_prompt_injection(content):
        return rejected_message("unsafe_directive")
    return {"role": "user", "content": scrub_pii(content)}


def prepare_messages(raw: object) -> list[dict[str, Any]]:
    """Sanitize current and historical turns; never replay rejected instructions.

    Only the server constructs message dictionaries on the public API. The
    rejection marker is internal metadata, never parsed from user text. Invalid
    graph-only history fails closed rather than passing arbitrary roles/objects.
    """
    if not isinstance(raw, list):
        return [rejected_message("malformed_messages")]
    if not raw:
        return [rejected_message("missing_user_message")]
    sanitized: list[dict[str, Any]] = []
    for message in raw:
        if not isinstance(message, dict) or message.get("role") not in ("user", "assistant"):
            return [rejected_message("malformed_messages")]
        if message["role"] == "user":
            code = message.get(REJECTION_KEY)
            if isinstance(code, str) and code in _REJECTION_CODES:
                sanitized.append(rejected_message(code))
            else:
                sanitized.append(prepare_user_message(message.get("content")))
        else:
            content = message.get("content")
            if not isinstance(content, str):
                return [rejected_message("malformed_messages")]
            sanitized.append({"role": "assistant", "content": scrub_pii(content)})
    if sanitized[-1]["role"] != "user":
        sanitized.append(rejected_message("missing_user_message"))
    return sanitized
