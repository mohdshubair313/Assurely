"""Allowlisted transport diagnostics for synthetic calibration; never raw errors."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any


def verdict_format(value: Any) -> str:
    """Classify response shape without retaining content or relaxing the parser."""
    if not isinstance(value, str):
        return "non_text"
    content = value.strip()
    if not content:
        return "empty"
    if content.startswith("```"):
        return "code_fence"
    try:
        json.loads(content)
    except ValueError:
        return "malformed_json" if content.startswith(("{", "[")) else "non_json_prefix"
    return "json"


def failure_category(status: int) -> str:
    return {
        400: "invalid_request",
        401: "authentication",
        402: "credit_limit",
        403: "forbidden",
        404: "endpoint_unavailable",
        408: "timeout",
        429: "rate_limited",
        502: "provider_unavailable",
        503: "provider_unavailable",
    }.get(status, "http_error")


def retry_after_seconds(value: Any, now: datetime | None = None) -> int | None:
    """Accept standard seconds/date forms; never retain arbitrary header text."""
    if not isinstance(value, str):
        return None
    try:
        if value.isascii() and value.isdecimal() and len(value) <= 8:
            seconds = int(value)
        else:
            target = parsedate_to_datetime(value)
            if target.tzinfo is None:
                return None
            seconds = math.ceil((target - (now or datetime.now(UTC))).total_seconds())
        return seconds if 0 <= seconds <= 86400 else None
    except (ValueError, TypeError, OverflowError):
        return None


def safe_usage(value: Any) -> dict[str, int | float]:
    """Provider usage is untrusted JSON; retain only finite numeric counters."""
    if not isinstance(value, dict):
        return {}
    result: dict[str, int | float] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens", "cost"):
        number = value.get(key)
        if (
            isinstance(number, (int, float))
            and not isinstance(number, bool)
            and 0 <= number <= 10**18
            and math.isfinite(number)
        ):
            result[key] = number
    details = value.get("completion_tokens_details")
    if isinstance(details, dict):
        count = details.get("reasoning_tokens")
        if type(count) is int and count >= 0:
            result["reasoning_tokens"] = count
    return result


def safe_quota(value: Any) -> dict[str, int]:
    """Keep only request counts, never account labels, key IDs or billing metadata."""
    if not isinstance(value, dict):
        return {}
    quota = value.get("free_model_daily_requests")
    if not isinstance(quota, dict):
        return {}
    return {
        key: quota[key]
        for key in ("used", "limit", "remaining")
        if type(quota.get(key)) is int and quota[key] >= 0
    }


def reliability_summary(calls: dict[str, Any], expected: int) -> dict[str, Any]:
    """Completion reliability and semantic agreement are distinct measurements."""
    from collections import Counter

    categories = Counter(
        v.get("failure_category", "unclassified")
        for v in calls.values()
        if v.get("status") != "parsed"
    )
    parsed = sum(v.get("status") == "parsed" for v in calls.values())
    return {
        "expected_cases": expected,
        "recorded_calls": len(calls),
        "usable_verdicts": parsed,
        "usable_fraction": parsed / expected if expected else 0,
        "missing_cases": max(0, expected - len(calls)),
        "failures": dict(categories),
    }
