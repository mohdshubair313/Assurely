"""Unit tests for FastAPI API endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.core.security import optional_authenticated_user_id, require_authenticated_user_id
from app.llm.providers import LLMResult
from app.main import app

client = TestClient(app)


def test_health_check() -> None:
    """Verify GET /health returns 200 and healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "environment" in data


def test_consent_endpoint() -> None:
    """Verify POST /v1/consent records grant and revoke actions."""
    user_id = UUID("00000000-0000-4000-8000-000000000123")
    app.dependency_overrides[require_authenticated_user_id] = lambda: user_id
    session = AsyncMock()
    session.execute.return_value = MagicMock(rowcount=0)
    session.execute.return_value.scalars.return_value.all.return_value = []
    session.__aenter__.return_value = session
    try:
        with patch("app.api.v1.consent.AsyncSessionLocal", return_value=session):
            res_grant = client.post(
                "/v1/consent",
                json={
                    "user_id": str(user_id),
                    "scope": "process_comparison",
                    "action": "grant",
                },
            )
            assert res_grant.status_code == 200
            assert res_grant.json()["status"] == "granted"

            res_revoke = client.post(
                "/v1/consent",
                json={
                    "user_id": str(user_id),
                    "scope": "save_profile",
                    "action": "revoke",
                },
            )
    finally:
        app.dependency_overrides.pop(require_authenticated_user_id, None)
    assert res_revoke.status_code == 200
    assert res_revoke.json()["status"] == "revoked"


def test_session_endpoint() -> None:
    """Verify GET /v1/session/{id} returns session state."""
    from types import SimpleNamespace

    from app.api.v1 import message as message_api

    checkpoint = SimpleNamespace(
        values={"messages": [{"role": "user", "content": "hi"}]}
    )
    db = AsyncMock()
    db.__aenter__.return_value = db
    db.get.return_value = None
    with (
        patch.object(message_api._app_graph, "aget_state", AsyncMock(return_value=checkpoint)),
        patch("app.api.v1.sessions.AsyncSessionLocal", return_value=db),
    ):
        response = client.get("/v1/session/sess-abc-123")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "sess-abc-123"
        assert data["status"] == "active"


def test_held_message_session_read_withholds_citations_and_calculators() -> None:
    """A held turn created through POST cannot leak claim data through GET."""
    from types import SimpleNamespace

    from app.api.v1 import message as message_api

    session_id = "held-session-2026"
    held_state = {
        "messages": [
            {"role": "user", "content": "synthetic test"},
            {"role": "assistant", "content": "unreleased synthetic advice"},
        ],
        "intent": "health",
        "approved": False,
        "escalation": True,
        "delivery_hold": True,
        "advisor_notification": {"status": "queued"},
        "output": {
            "report_status": "ready",
            "reply": "Synthetic report",
            "sentences": [{"text": "Synthetic report"}],
        },
        "retrieved_facts": [{"claim": "withheld citation", "source": "test"}],
        "calculator_outputs": {"recommended_cover": 123456},
    }
    checkpoint = SimpleNamespace(values=held_state)
    graph = MagicMock()
    graph.aget_state = AsyncMock(side_effect=[None, checkpoint])
    graph.ainvoke = AsyncMock(return_value=held_state)
    db = AsyncMock()
    db.__aenter__.return_value = db
    db.get.return_value = None

    with (
        patch.object(message_api, "_app_graph", graph),
        patch("app.api.v1.message.AsyncSessionLocal", return_value=db),
        patch("app.api.v1.sessions.AsyncSessionLocal", return_value=db),
    ):
        post = client.post(
            "/v1/message",
            json={"session_id": session_id, "user_message": "synthetic test"},
        )
        assert post.status_code == 200
        assert post.json()["delivery_hold"] is True
        assert post.json()["citations"] == []
        assert post.json()["calculator_outputs"] == {}

        get = client.get(f"/v1/session/{session_id}")

    assert get.status_code == 200
    data = get.json()
    assert data["citations"] == []
    assert data["calculator_outputs"] == {}
    assert data["messages"] == []


@pytest.mark.parametrize(
    "hold_reason",
    ["delivery_hold", "approval", "escalation", "notification", "report_not_ready"],
)
def test_session_read_rechecks_each_delivery_gate(hold_reason: str) -> None:
    """Attempt to recover held data when exactly one delivery condition blocks it."""
    from types import SimpleNamespace

    from app.api.v1 import message as message_api

    state = {
        "messages": [
            {"role": "user", "content": "synthetic test"},
            {"role": "assistant", "content": "unreleased synthetic advice"},
        ],
        "intent": "health",
        "approved": True,
        "escalation": False,
        "delivery_hold": False,
        "advisor_notification": {},
        "output": {
            "report_status": "ready",
            "reply": "Synthetic report",
            "sentences": [{"text": "Synthetic report"}],
        },
        "retrieved_facts": [{"claim": "attack citation", "source": "test"}],
        "calculator_outputs": {"cover": 987654},
    }
    if hold_reason == "delivery_hold":
        state["delivery_hold"] = True
    elif hold_reason == "approval":
        state["approved"] = False
    elif hold_reason == "escalation":
        state["escalation"] = True
    elif hold_reason == "notification":
        state["advisor_notification"] = {"status": "queued"}
    else:
        state["output"]["report_status"] = "pending"

    graph = MagicMock()
    graph.aget_state = AsyncMock(return_value=SimpleNamespace(values=state))
    db = AsyncMock()
    db.__aenter__.return_value = db
    db.get.return_value = None

    with (
        patch.object(message_api, "_app_graph", graph),
        patch("app.api.v1.sessions.AsyncSessionLocal", return_value=db),
    ):
        response = client.get(f"/v1/session/attack-{hold_reason}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["citations"] == []
    assert payload["calculator_outputs"] == {}
    assert payload["messages"] == []


def test_post_message_endpoint() -> None:
    """Verify POST /v1/message invokes graph pipeline."""
    app.dependency_overrides[optional_authenticated_user_id] = lambda: UUID(
        "00000000-0000-4000-8000-000000000123"
    )
    mock_llm_json = (
        '{"age": 28, "city_tier": "tier_1", "dependents": 0, '
        '"pre_existing_conditions": false, "existing_coverage": 0}'
    )

    # Exercise the real graph with an empty terms result, without a live database.
    # Stage 3 added this dependency after the endpoint test was originally written.
    db_result = MagicMock()
    db_result.all.return_value = []
    db_result.scalar_one.return_value = UUID("00000000-0000-4000-8000-000000000123")
    db_result.scalars.return_value.all.return_value = []
    db_session = AsyncMock()
    db_session.execute.return_value = db_result
    db_session.__aenter__.return_value = db_session
    db_session.commit = AsyncMock()
    db_session.add = MagicMock()
    try:
        with (
            patch("app.graph.nodes.needs_intake.llm_call") as mock_llm,
            patch(
                "app.graph.nodes.intent_router.llm_call",
                return_value=LLMResult(
                    content='{"intent":"health"}',
                    provider="mock",
                    model="mock-router",
                    total_tokens=3,
                ),
            ),
            patch("app.graph.nodes.compare_verify.AsyncSessionLocal", return_value=db_session),
            patch("app.graph.nodes.persist_memory.AsyncSessionLocal", return_value=db_session),
            patch("app.api.v1.message.AsyncSessionLocal", return_value=db_session),
        ):
            mock_llm.return_value = LLMResult(
                content=mock_llm_json,
                provider="mock",
                model="mock-groq",
                total_tokens=25,
            )

            response = client.post(
                "/v1/message",
                json={
                    "session_id": "test-sess-999",
                    "user_id": "00000000-0000-4000-8000-000000000123",
                    "user_message": "I am 28 living in Mumbai with no diseases. Just for me.",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["session_id"] == "test-sess-999"
            assert "calculator_outputs" in data
            assert data["calculator_outputs"] == {}
            assert data["escalation"] is True
            assert data["delivery_hold"] is True
            assert data["guardrail_notes"] == []
            assert data["draft_output"] == {}
            assert data["output"] == {}
    finally:
        app.dependency_overrides.pop(optional_authenticated_user_id, None)
