"""Unit tests for FastAPI API endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

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
    with patch.object(message_api._app_graph, "aget_state", AsyncMock(return_value=checkpoint)):
        response = client.get("/v1/session/sess-abc-123")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "sess-abc-123"
        assert data["status"] == "active"


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
