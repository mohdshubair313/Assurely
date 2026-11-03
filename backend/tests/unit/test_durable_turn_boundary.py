"""Non-development message execution invalidates durable authority before graph work."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.parametrize("fails", [False, True])
def test_begin_precedes_graph_and_failure_finishes_without_report(fails):
    order = []
    turn = uuid.uuid4()

    async def begin(*args):
        order.append("begin")
        return turn

    async def graph(*args, **kwargs):
        order.append("graph")
        if fails:
            raise ValueError("Synthetic failure")
        return {"input_status": "rejected", "intent": "health"}

    async def finish(db, issuer, key, current_turn, state):
        order.append("finish")
        assert current_turn == turn
        assert state is None if fails else state["input_status"] == "rejected"

    db = AsyncMock()
    db.__aenter__.return_value = db
    db.begin = MagicMock(return_value=AsyncMock())
    with (
        patch("app.api.v1.message.get_settings", return_value=SimpleNamespace(
            environment="production", auth_issuer="https://issuer.test/")),
        patch("app.api.v1.message.AsyncSessionLocal", return_value=db),
        patch("app.api.v1.message._app_graph", SimpleNamespace(
            aget_state=AsyncMock(return_value=None), ainvoke=graph)),
        patch("app.api.v1.message.report_release.begin_turn", begin),
        patch("app.api.v1.message.report_release.finish_turn", finish),
    ):
        response = TestClient(app).post(
            "/v1/message", json={"user_message": "Explain health cover"},
        )
    assert response.status_code == (500 if fails else 200)
    assert order == ["begin", "graph", "finish"]
