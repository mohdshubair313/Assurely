"""Privacy and behavior contracts for Langfuse graph instrumentation."""

from contextlib import contextmanager
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.core.tracing import observation, trace_node


@pytest.mark.asyncio
async def test_trace_node_preserves_behavior_without_recording_state_values() -> None:
    """Graph traces keep structural context but omit profile and report content."""
    span = Mock()
    node = AsyncMock(return_value={"approved": True, "output": {"claim": "private"}})

    @contextmanager
    def fake_observation(*args: object, **kwargs: object):
        yield span

    state = {"user_profile": {"age": 42}, "messages": [{"content": "private"}]}
    with patch("app.core.tracing.observation", fake_observation):
        result = await trace_node("guardrail", node)(state)

    assert result == {"approved": True, "output": {"claim": "private"}}
    node.assert_awaited_once_with(state)
    traced_output = span.update.call_args.kwargs["output"]
    assert traced_output == {"result_fields": ["approved", "output"], "approved": True}
    assert "private" not in repr(traced_output)


def test_observation_is_a_noop_outside_a_traced_request() -> None:
    """Direct graph/unit runs do not emit telemetry without an API trace context."""
    with patch("app.core.tracing._get_client") as get_client, observation("test-operation") as span:
        assert span is None
    get_client.assert_not_called()


@pytest.mark.asyncio
async def test_trace_node_records_report_counts_without_report_content() -> None:
    private_text = "PRIVATE_POLICY_CLAUSE_SENTINEL"
    span = Mock()
    node = AsyncMock(
        return_value={
            "output": {
                "report_status": "ready",
                "evidence_count": 2,
                "sentences": [{"text": private_text, "citations": [{"source": private_text}]}],
            }
        }
    )

    @contextmanager
    def fake_observation(*args: object, **kwargs: object):
        yield span

    with (
        patch("app.core.tracing._active_trace") as active,
        patch("app.core.tracing.observation", fake_observation),
    ):
        active.get.return_value = True
        result = await trace_node("explanation-report", node)({"session_id": "s"})

    assert result["output"]["sentences"][0]["text"] == private_text
    traced_output = span.update.call_args.kwargs["output"]
    assert traced_output == {
        "result_fields": ["output"],
        "report_status": "ready",
        "evidence_count": 2,
        "report_sentence_count": 1,
    }
    assert private_text not in repr(traced_output)
