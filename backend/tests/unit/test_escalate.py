"""Notification transport, replay and independent delivery-hold contracts."""

from contextlib import contextmanager
from copy import deepcopy
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.graph.nodes.escalate import _event_id, escalate_node
from app.graph.state import create_initial_state


def review_state():
    state = create_initial_state("synthetic-review")
    state.update(approved=True, escalation=True, escalation_reason="Synthetic review required",
                 missing_fields=[], output={"reply": "WITHHELD_REPORT", "source": "synthetic"})
    return state


def settings(**overrides):
    return Settings(_env_file=None, **{
        "advisor_webhook_url": "https://advisor.example.test/queue",
        "advisor_webhook_retry_delay_seconds": 0,
        **overrides,
    })


@contextmanager
def transport(handler, **overrides):
    real_client = httpx.AsyncClient
    with (
        patch("app.graph.nodes.escalate.get_settings", return_value=settings(**overrides)),
        patch("app.graph.nodes.escalate.httpx.AsyncClient", side_effect=lambda **kwargs:
              real_client(transport=httpx.MockTransport(handler), **kwargs)),
    ):
        yield


def queued(request):
    event = json.loads(request.content)
    assert request.headers["Idempotency-Key"] == event["event_id"]
    assert "output" not in event and "user_profile" not in event
    assert event["delivery_hold"] is True
    return httpx.Response(202, json={"queued": True, "event_id": event["event_id"]})


@pytest.mark.asyncio
async def test_clean_case_does_not_notify():
    state = review_state()
    state["escalation"] = False
    with patch("app.graph.nodes.escalate.dispatch_notification") as send:
        result = await escalate_node(state)
    send.assert_not_called()
    assert result == {"delivery_hold": False, "advisor_notification": {}}


@pytest.mark.asyncio
@pytest.mark.parametrize("approved", [True, False])
async def test_notification_success_still_holds_and_never_mutates_output(approved):
    state = review_state()
    state["approved"] = approved
    original = deepcopy(state)
    with transport(queued):
        result = await escalate_node(state)
    assert result["delivery_hold"] is True
    assert result["advisor_notification"]["status"] == "queued"
    assert "output" not in result
    assert state == original


@pytest.mark.asyncio
async def test_unapproved_case_holds_even_if_escalation_flag_is_false():
    state = review_state()
    state.update(approved=False, escalation=False)
    with transport(queued):
        result = await escalate_node(state)
    assert result["delivery_hold"] is True


@pytest.mark.asyncio
async def test_missing_destination_holds_without_sending():
    with transport(lambda request: pytest.fail("Must not send"), advisor_webhook_url=""):
        result = await escalate_node(review_state())
    assert result["delivery_hold"] is True
    assert result["advisor_notification"]["status"] == "unconfigured"
    assert result["advisor_notification"]["attempts"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("url,environment", [
    ("http://advisor.example.test/queue", "development"),
    ("http://127.0.0.1:9999/queue", "production"),
    ("https://user:password@advisor.example.test/queue", "production"),
    ("https://advisor.example.test/queue#fragment", "development"),
])
async def test_invalid_destination_cannot_release_or_transmit(url, environment):
    with transport(lambda request: pytest.fail("Must not send"),
                   advisor_webhook_url=url, environment=environment):
        result = await escalate_node(review_state())
    assert result["delivery_hold"] is True
    assert result["advisor_notification"]["error"] == "invalid_destination"


@pytest.mark.asyncio
async def test_token_transmitted_only_in_authorization_header():
    def handler(request):
        assert request.headers["Authorization"] == "Bearer synthetic-token"
        assert "synthetic-token" not in request.content.decode()
        return queued(request)
    with transport(handler, advisor_webhook_token=SecretStr("synthetic-token")):
        result = await escalate_node(review_state())
    assert "synthetic-token" not in json.dumps(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("first_failure", [429, 503, "timeout"])
async def test_transient_failure_retries_same_event(first_failure):
    keys = []
    def handler(request):
        keys.append(request.headers["Idempotency-Key"])
        if len(keys) == 1:
            if first_failure == "timeout":
                raise httpx.ReadTimeout("Synthetic timeout", request=request)
            return httpx.Response(first_failure)
        return queued(request)
    with transport(handler):
        result = await escalate_node(review_state())
    assert len(keys) == 2 and keys[0] == keys[1]
    assert result["advisor_notification"]["status"] == "queued"
    assert "error" not in result["advisor_notification"]
    assert result["delivery_hold"] is True


@pytest.mark.asyncio
async def test_persistent_failure_has_bounded_retries_and_holds():
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(503, text="Private receiver details")
    with transport(handler):
        result = await escalate_node(review_state())
    assert len(requests) == 3
    assert result["delivery_hold"] is True
    assert result["advisor_notification"]["status"] == "failed"
    assert "Private receiver details" not in json.dumps(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [
    httpx.Response(401), httpx.Response(302, headers={"Location": "https://elsewhere.test"}),
    httpx.Response(204), httpx.Response(200, text="OK"),
    httpx.Response(202, json={"queued": True, "event_id": "wrong-event"}),
    httpx.Response(200, json={"queued": False}),
])
async def test_rejection_or_unconfirmed_ack_never_counts_as_queued(response):
    requests = []
    def handler(request):
        requests.append(request)
        return response
    with transport(handler):
        result = await escalate_node(review_state())
    assert len(requests) == 1
    assert result["advisor_notification"]["status"] == "failed"
    assert result["delivery_hold"] is True


@pytest.mark.asyncio
async def test_replay_skips_confirmed_event_but_changed_case_notifies():
    requests = []
    def handler(request):
        requests.append(request)
        return queued(request)
    state = review_state()
    with transport(handler):
        state.update(await escalate_node(state))
        state.update(await escalate_node(state))
        assert len(requests) == 1
        state["output"] = {"reply": "A different synthetic report"}
        state.update(await escalate_node(state))
    assert len(requests) == 2
    assert requests[0].headers["Idempotency-Key"] != requests[1].headers["Idempotency-Key"]
    assert state["delivery_hold"] is True


def test_event_identity_ignores_capture_times_but_preserves_verification_dates():
    state = review_state()
    state["draft_output"] = {"generated_at": "first", "cited_facts": [
        {"retrieved_at": "first", "last_verified": "2026-09-25"}]}
    identity = _event_id(state)
    state["draft_output"]["generated_at"] = "second"
    state["draft_output"]["cited_facts"][0]["retrieved_at"] = "second"
    assert _event_id(state) == identity
    state["draft_output"]["cited_facts"][0]["last_verified"] = "2026-09-26"
    assert _event_id(state) != identity


@pytest.mark.asyncio
async def test_later_clean_pass_does_not_clear_existing_review_hold():
    state = review_state()
    with transport(queued):
        state.update(await escalate_node(state))
        state.update(approved=True, escalation=False)
        result = await escalate_node(state)
    assert result["delivery_hold"] is True


@pytest.mark.asyncio
async def test_unexpected_dispatch_error_fails_closed():
    with patch("app.graph.nodes.escalate.dispatch_notification", new=AsyncMock(side_effect=RuntimeError("private"))):
        result = await escalate_node(review_state())
    assert result["delivery_hold"] is True
    assert result["advisor_notification"]["status"] == "failed"
    assert "private" not in json.dumps(result)
