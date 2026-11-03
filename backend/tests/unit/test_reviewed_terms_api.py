"""Import authority and per-turn scenario boundaries for reviewed policy terms."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1 import message as message_api
from app.api.v1 import policy_publications as api
from app.api.v1.policy_reviews import review_db
from app.graph.nodes import compare_verify
from app.main import app as main_app
from tests.unit.test_policy_review_api import DIGEST, SUBJECT, token
from tests.unit.test_policy_review_api import setup as _review_setup

review_setup = _review_setup


@pytest.fixture
def setup(review_setup):
    app, client, key, settings = review_setup
    settings.policy_publisher_subjects = []
    app.include_router(api.router, prefix="/v1")
    return app, client, key, settings


def test_term_import_requires_independent_publisher_authorization(setup, monkeypatch):
    app, client, key, settings = setup
    path = "/v1/policy-publications/" + DIGEST + "/term-import"
    body = {"request_key": str(uuid.uuid4()), "publication_event_id": str(uuid.uuid4())}
    assert client.post(path, json=body).status_code == 401
    assert client.post(path, json=body, headers=token(key)).status_code == 503
    settings.policy_publisher_subjects = [str(uuid.uuid4())]
    assert client.post(path, json=body, headers=token(key, roles=["publisher"])).status_code == 403
    settings.policy_publisher_subjects = [str(SUBJECT)]

    async def db():
        yield object()

    app.dependency_overrides[review_db] = db
    mocked = AsyncMock(return_value={"status": "imported", "requires_fresh_lookup": True})
    monkeypatch.setattr(api.reviewed_policy_terms, "import_terms", mocked)
    assert (
        client.post(
            path, json={**body, "reviewer_id": str(uuid.uuid4())}, headers=token(key)
        ).status_code
        == 422
    )
    assert client.post(path, json=body, headers=token(key)).status_code == 200
    assert mocked.await_args.args[1].subject == SUBJECT
    assert mocked.await_count == 1


def scenario():
    return {
        "items": [
            {
                "publication_digest": DIGEST,
                "capabilities": ["coverage_options"],
                "context": {
                    "transaction": "issue",
                    "transaction_date": "2026-11-02",
                    "cover_basis": "individual",
                    "selected_options": [],
                },
            }
        ]
    }


def test_scenario_is_explicitly_replaced_each_turn(monkeypatch):
    graph = MagicMock()
    graph.aget_state = AsyncMock(return_value=None)
    graph.ainvoke = AsyncMock(return_value={"delivery_hold": True, "approved": False})
    monkeypatch.setattr(message_api, "_app_graph", graph)
    client = TestClient(main_app)
    first = client.post(
        "/v1/message",
        json={
            "session_id": "scenario-check",
            "user_message": "Compare these terms",
            "reviewed_comparison_request": scenario(),
        },
    )
    assert first.status_code == 200 and first.json()["delivery_hold"] is True
    assert graph.ainvoke.await_args.args[0]["reviewed_comparison_request"] == scenario() | {
        "items": [
            {
                **scenario()["items"][0],
                "context": {
                    **scenario()["items"][0]["context"],
                    "entry_age_years": None,
                    "residency": None,
                    "zone": None,
                    "portability": None,
                    "continuity": None,
                },
            }
        ]
    }
    graph.aget_state.return_value = SimpleNamespace(
        values={
            "messages": [{"role": "user", "content": "Compare these terms"}],
            "user_id": None,
            "reviewed_comparison_request": scenario(),
        }
    )
    second = client.post(
        "/v1/message", json={"session_id": "scenario-check", "user_message": "Another question"}
    )
    assert second.status_code == 200
    assert graph.ainvoke.await_args.args[0]["reviewed_comparison_request"] is None


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value["items"][0]["context"].pop("selected_options"),
        lambda value: value["items"][0]["context"].pop("transaction_date"),
        lambda value: value["items"][0]["capabilities"].append("premium"),
        lambda value: value.update(approved=True),
    ],
)
def test_invalid_scenario_never_reaches_graph(monkeypatch, change):
    graph = MagicMock()
    graph.aget_state = AsyncMock()
    graph.ainvoke = AsyncMock()
    monkeypatch.setattr(message_api, "_app_graph", graph)
    body = scenario()
    change(body)
    response = TestClient(main_app).post(
        "/v1/message", json={"user_message": "Please compare", "reviewed_comparison_request": body}
    )
    assert response.status_code == 422
    graph.aget_state.assert_not_awaited()
    graph.ainvoke.assert_not_awaited()


def test_duplicate_scenario_fields_never_reach_graph(monkeypatch):
    graph = MagicMock()
    graph.aget_state = AsyncMock()
    monkeypatch.setattr(message_api, "_app_graph", graph)
    raw = (
        '{"user_message":"Compare", "reviewed_comparison_request":null, '
        '"reviewed_comparison_request":null}'
    )
    response = TestClient(main_app).post(
        "/v1/message", content=raw, headers={"content-type": "application/json"}
    )
    assert response.status_code == 422
    graph.aget_state.assert_not_awaited()


async def test_database_failure_and_missing_config_never_enable_graph_fallback(monkeypatch):
    monkeypatch.setattr(
        compare_verify,
        "get_settings",
        lambda: SimpleNamespace(environment="production", auth_issuer="https://identity.example/"),
    )

    def broken_db():
        raise SQLAlchemyError("must not leak")

    monkeypatch.setattr(compare_verify, "AsyncSessionLocal", broken_db)
    result = await compare_verify.compare_verify_node({"reviewed_comparison_request": scenario()})
    assert result["draft_output"]["publication_gate"] == "blocked"
    assert result["draft_output"]["need_fit_view"] == []
    assert "reviewed_comparison" not in result["draft_output"]
