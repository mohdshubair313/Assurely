"""Unit tests for FastAPI API endpoints."""

from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from app.main import app
from app.llm.providers import LLMResult

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
    res_grant = client.post(
        "/v1/consent",
        json={"user_id": "usr-123", "scope": "process_comparison", "action": "grant"},
    )
    assert res_grant.status_code == 200
    assert res_grant.json()["status"] == "granted"

    res_revoke = client.post(
        "/v1/consent",
        json={"user_id": "usr-123", "scope": "save_profile", "action": "revoke"},
    )
    assert res_revoke.status_code == 200
    assert res_revoke.json()["status"] == "revoked"


def test_session_endpoint() -> None:
    """Verify GET /v1/session/{id} returns session state."""
    response = client.get("/v1/session/sess-abc-123")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "sess-abc-123"
    assert data["status"] == "active"


def test_post_message_endpoint() -> None:
    """Verify POST /v1/message invokes graph pipeline."""
    mock_llm_json = '{"age": 28, "city_tier": "tier_1", "dependents": 0, "pre_existing_conditions": false, "existing_coverage": 0}'

    # Exercise the real graph with an empty terms result, without a live database.
    # Stage 3 added this dependency after the endpoint test was originally written.
    db_result = MagicMock()
    db_result.all.return_value = []
    db_session = AsyncMock()
    db_session.execute.return_value = db_result
    db_session.__aenter__.return_value = db_session
    with (
        patch("app.graph.nodes.needs_intake.llm_call") as mock_llm,
        patch("app.graph.nodes.compare_verify.AsyncSessionLocal", return_value=db_session),
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
