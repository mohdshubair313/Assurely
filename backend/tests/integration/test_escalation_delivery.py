"""Actual loopback HTTP proof, with no external network or advisor contact."""

import pytest

from eval.escalation_preflight import run_preflight


@pytest.mark.asyncio
async def test_notification_commit_retry_concurrency_and_api_hold():
    report = await run_preflight()
    assert report["http_requests"] == 4  # One retry and two lost-checkpoint replays.
    assert report["unique_queued_events"] == 1
    assert report["graph_output_unchanged"] is True
    assert report["delivery_hold_after_queue_ack"] is True
    assert report["public_response"]["output"] == {}
