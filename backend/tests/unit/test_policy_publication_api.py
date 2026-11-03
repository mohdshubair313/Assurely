"""Signed publisher authority, bounded JSON inputs and legacy production containment."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1 import policy_publications as api
from app.api.v1.policy_reviews import review_db
from app.db import policy_publication_store as store
from tests.unit.test_policy_review_api import DIGEST, SUBJECT, token
from tests.unit.test_policy_review_api import setup as _review_setup

review_setup = _review_setup


@pytest.fixture
def setup(review_setup):
    app, client, key, settings = review_setup
    app.include_router(api.router, prefix="/v1")
    settings.policy_publisher_subjects = []
    return app, client, key, settings


@pytest.mark.parametrize(
    "method,suffix",
    [
        ("GET", "/requirements/" + DIGEST),
        ("POST", ""),
        ("GET", "/" + DIGEST),
        ("POST", "/" + DIGEST + "/decisions"),
        ("POST", "/" + DIGEST + "/lookup"),
    ],
)
def test_anonymous_cannot_reach_storage(setup, method, suffix):
    assert setup[1].request(method, "/v1/policy-publications" + suffix).status_code == 401


def test_reviewer_and_claimed_roles_do_not_grant_publisher_authority(setup):
    _, client, key, settings = setup
    path = "/v1/policy-publications/" + DIGEST + "/decisions"
    assert client.post(path, json={}, headers=token(key)).status_code == 503
    settings.policy_publisher_subjects = [str(uuid.uuid4())]
    assert client.post(path, json={}, headers=token(key, roles=["publisher"])).status_code == 403
    settings.policy_publisher_subjects = ["invalid-subject"]
    assert client.post(path, json={}, headers=token(key)).status_code == 503


def allow_db(app):
    async def db():
        yield object()

    app.dependency_overrides[review_db] = db


def test_publish_actor_is_verified_and_body_cannot_spoof_it(setup, monkeypatch):
    app, client, key, settings = setup
    settings.policy_publisher_subjects = [str(SUBJECT)]
    allow_db(app)
    decide = AsyncMock(
        return_value={"action": "publish", "scope": "historical_publication_receipt"}
    )
    monkeypatch.setattr(store, "decide", decide)
    body = {
        "request_key": str(uuid.uuid4()),
        "expected_revision": 0,
        "representation_event_id": str(uuid.uuid4()),
        "action": "publish",
        "reason": "Synthetic review",
        "expires_at": "2026-11-03T00:00:00Z",
    }
    path = "/v1/policy-publications/" + DIGEST + "/decisions"
    response = client.post(path, json=body, headers=token(key))
    assert response.status_code == 200
    assert decide.await_args.args[1].subject == SUBJECT
    assert decide.await_args.args[3].expires_at.tzinfo is not None
    assert (
        client.post(
            path, json={**body, "reviewer_id": str(uuid.uuid4())}, headers=token(key)
        ).status_code
        == 422
    )
    assert decide.await_count == 1


@pytest.mark.parametrize("suffix", ["", "/" + DIGEST + "/decisions", "/" + DIGEST + "/lookup"])
def test_duplicate_keys_and_overlimit_bodies_are_rejected(setup, suffix):
    app, client, key, settings = setup
    allow_db(app)
    settings.policy_publisher_subjects = [str(SUBJECT)]
    path = "/v1/policy-publications" + suffix
    response = client.post(
        path, content='{"request_key":"a","request_key":"b"}', headers=token(key)
    )
    assert response.status_code == 422
    response = client.post(path, content=" " * 512_001, headers=token(key))
    assert response.status_code == 413


def test_lookup_rejects_client_approval_and_unsupported_premium(setup, monkeypatch):
    app, client, key, _ = setup
    allow_db(app)
    mock = AsyncMock(return_value={"status": "unavailable", "facts": []})
    monkeypatch.setattr(store, "lookup", mock)
    body = {
        "capability": "coverage_options",
        "context": {
            "transaction": "issue",
            "transaction_date": "2026-11-02",
            "cover_basis": "individual",
            "selected_options": [],
        },
    }
    path = "/v1/policy-publications/" + DIGEST + "/lookup"
    assert client.post(path, json=body, headers=token(key)).status_code == 200
    assert client.post(path, json={**body, "approved": True}, headers=token(key)).status_code == 422
    body["capability"] = "premium"
    assert client.post(path, json=body, headers=token(key)).status_code == 422
    assert mock.await_count == 1


@pytest.mark.parametrize("environment", ["production", "staging", "unexpected"])
async def test_legacy_seed_comparison_is_blocked_outside_development(monkeypatch, environment):
    from app.graph.nodes import compare_verify, guardrail

    monkeypatch.setattr(
        compare_verify, "get_settings", lambda: SimpleNamespace(environment=environment)
    )

    def forbidden_db():
        raise AssertionError("Legacy seed terms were queried")

    monkeypatch.setattr(compare_verify, "AsyncSessionLocal", forbidden_db)
    result = await compare_verify.compare_verify_node({"user_profile": {"age": 35}})
    assert result["draft_output"]["publication_gate"] == "blocked"
    assert result["draft_output"]["need_fit_view"] == []
    checked = await guardrail.guardrail_node(result)
    assert checked["approved"] is False and checked["escalation"] is True
    assert "output" not in checked and "output" not in result
