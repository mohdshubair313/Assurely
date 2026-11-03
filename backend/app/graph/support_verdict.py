"""Strict, dependency-free verdict parsing shared by runtime and calibration."""

from __future__ import annotations

import json
from typing import Any


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate verdict key")
        result[key] = value
    return result


def parse_verdict(content: str, finish_reason: str, expected: set[int]) -> dict[str, Any]:
    """Reject incomplete, duplicate, extra, missing, or incorrectly typed verdicts."""
    if finish_reason != "stop":
        raise ValueError("incomplete_verdict")
    parsed = json.loads(content, object_pairs_hook=_unique_keys)
    if not isinstance(parsed, dict) or set(parsed) != {"verdicts"}:
        raise ValueError("invalid_verdict")
    verdicts = parsed["verdicts"]
    if not isinstance(verdicts, list) or len(verdicts) != len(expected):
        raise ValueError("invalid_verdict")
    seen: set[int] = set()
    for item in verdicts:
        if (
            not isinstance(item, dict)
            or set(item) != {"sentence_id", "verdict"}
            or type(item["sentence_id"]) is not int
            or item["sentence_id"] not in expected
            or item["sentence_id"] in seen
            or item["verdict"] not in ("supported", "unsupported", "uncertain")
        ):
            raise ValueError("invalid_verdict")
        seen.add(item["sentence_id"])
    return parsed
