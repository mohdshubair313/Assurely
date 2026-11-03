"""Transport evidence must separate failures without copying provider secrets."""

import io
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from eval.claim_support_experiment import infer
from eval.claim_support_live import quota_preflight
from eval.provider_diagnostics import reliability_summary, retry_after_seconds, safe_usage


@pytest.mark.parametrize(
    "header,expected",
    [
        ("30", 30),
        ("0", 0),
        ("-1", None),
        ("1e3", None),
        ("999999999", None),
        ("private-token", None),
        (None, None),
        ("Sat, 24 Oct 2026 12:01:00 GMT", 60),
    ],
)
def test_retry_after_is_bounded_and_does_not_echo_text(header, expected):
    assert retry_after_seconds(header, datetime(2026, 10, 24, 12, tzinfo=UTC)) == expected


def test_usage_drops_untrusted_strings_nested_fields_and_nonfinite_values():
    value = {
        "prompt_tokens": 123,
        "completion_tokens": True,
        "total_tokens": float("nan"),
        "cost": 0,
        "private": "secret",
        "prompt_tokens_details": {"secret": "private"},
        "completion_tokens_details": {"reasoning_tokens": 45, "secret": "private"},
    }
    assert safe_usage(value) == {"prompt_tokens": 123, "cost": 0, "reasoning_tokens": 45}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,code,category",
    [
        (429, 429, "rate_limited"),
        (404, 404, "endpoint_unavailable"),
        (200, 429, "rate_limited"),
        (200, "secret-code", "provider_error"),
    ],
)
async def test_http_and_embedded_errors_are_classified_without_raw_content(
    monkeypatch, status, code, category
):
    monkeypatch.setenv("OPENROUTER_API_KEY", "private-credential")
    response = httpx.Response(
        status,
        request=httpx.Request("POST", "https://example.invalid"),
        headers={"retry-after": "12"},
        json={
            "error": {"code": code, "message": "private-credential", "metadata": {"raw": "private"}}
        },
    )
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=response)) as post:
        output, info = await infer("[]", "prompt")
    post.assert_awaited_once()
    assert output is None and info["failure_category"] == category
    assert info["retry_after_seconds"] == 12
    assert "private" not in json.dumps(info) and "secret-code" not in json.dumps(info)


def test_reliability_does_not_drop_failed_or_unrecorded_cases():
    report = reliability_summary(
        {
            "S1": {"status": "parsed"},
            "U1": {"status": "failed", "failure_category": "rate_limited"},
        },
        3,
    )
    assert report["usable_fraction"] == 1 / 3
    assert report["missing_cases"] == 1 and report["failures"] == {"rate_limited": 1}


@pytest.mark.asyncio
async def test_timeout_is_distinct_from_malformed_response(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "private-credential")
    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=httpx.ReadTimeout("private"))):
        output, info = await infer("[]", "prompt")
    assert output is None and info["failure_category"] == "timeout"


@pytest.mark.parametrize("remaining,allowed", [(11, False), (12, True), (0, False)])
def test_known_insufficient_quota_prevents_cohort_without_retaining_key(remaining, allowed):
    body = {
        "data": {
            "label": "private-key-label",
            "free_model_daily_requests": {
                "used": 10,
                "limit": 50,
                "remaining": remaining,
                "extra": "private",
            },
        }
    }
    with patch("urllib.request.urlopen", return_value=io.StringIO(json.dumps(body))):
        result = quota_preflight({"OPENROUTER_API_KEY": "private-credential"}, 12)
    assert result["allowed"] is allowed and result["quota_known"]
    assert "private" not in json.dumps(result)


def test_quota_failure_is_not_treated_as_permission_to_run():
    with patch("urllib.request.urlopen", side_effect=RuntimeError("private-credential")):
        result = quota_preflight({"OPENROUTER_API_KEY": "private-credential"}, 12)
    assert not result["allowed"] and result["status"] == "unavailable"
    assert "private" not in json.dumps(result)
