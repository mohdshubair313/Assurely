"""The internal comparison requires verified reviewer access and explicit scope."""

import json
from unittest.mock import AsyncMock

import pytest

from app.api.v1 import policy_publications as api
from app.api.v1.policy_reviews import review_db
from tests.unit.test_policy_review_api import DIGEST, SUBJECT, token
from tests.unit.test_policy_review_api import setup as _review_setup

review_setup = _review_setup


@pytest.fixture
def setup(review_setup):
    app, client, key, settings = review_setup
    app.include_router(api.router, prefix="/v1")
    return app, client, key, settings


def payload():
    return {
        "items": [
            {
                "publication_digest": DIGEST,
                "capabilities": ["coverage_options", "base_ped_wait"],
                "context": {
                    "transaction": "issue",
                    "transaction_date": "2026-11-02",
                    "cover_basis": "individual",
                    "selected_options": [],
                },
            }
        ]
    }


def allow_db(app):
    async def db():
        yield object()

    app.dependency_overrides[review_db] = db


def test_unauthorized_request_never_reaches_storage(setup):
    _, client, key, settings = setup
    path = "/v1/policy-publications/comparisons"
    assert client.post(path, json=payload()).status_code == 401
    settings.policy_reviewer_subjects = []
    assert client.post(path, json=payload(), headers=token(key)).status_code == 503
    settings.policy_reviewer_subjects = ["00000000-0000-4000-8000-000000000999"]
    assert (
        client.post(path, json=payload(), headers=token(key, roles=["reviewer"])).status_code == 403
    )


def test_verified_subject_and_explicit_scenario_reach_service(setup, monkeypatch):
    app, client, key, _ = setup
    allow_db(app)
    compare = AsyncMock(return_value={"status": "partial", "customer_delivery_authorized": False})
    monkeypatch.setattr(api.reviewed_comparison, "compare", compare)
    response = client.post(
        "/v1/policy-publications/comparisons", json=payload(), headers=token(key)
    )
    assert response.status_code == 200
    assert response.json()["customer_delivery_authorized"] is False
    assert compare.await_args.args[1].subject == SUBJECT
    command = compare.await_args.args[2]
    assert command.items[0].context.transaction_date.isoformat() == "2026-11-02"
    assert command.items[0].context.selected_options == []


@pytest.mark.parametrize(
    "change",
    [
        lambda b: b["items"][0]["context"].pop("transaction_date"),
        lambda b: b["items"][0]["context"].pop("selected_options"),
        lambda b: b["items"][0]["context"].update(transaction="revision"),
        lambda b: b["items"][0]["context"].update(entry_age_years=True),
        lambda b: b["items"][0]["capabilities"].append("premium"),
        lambda b: b["items"][0]["capabilities"].append("coverage_options"),
        lambda b: b["items"].append(b["items"][0].copy()),
        lambda b: b.update(customer_delivery_authorized=True),
        lambda b: b["items"][0].update(issuer="https://other.test"),
    ],
)
def test_incomplete_ambiguous_or_forged_requests_fail_before_comparison(setup, monkeypatch, change):
    app, client, key, _ = setup
    allow_db(app)
    compare = AsyncMock()
    monkeypatch.setattr(api.reviewed_comparison, "compare", compare)
    body = payload()
    change(body)
    response = client.post("/v1/policy-publications/comparisons", json=body, headers=token(key))
    assert response.status_code == 422
    compare.assert_not_awaited()


def test_duplicate_json_and_request_size_are_bounded(setup, monkeypatch):
    app, client, key, _ = setup
    allow_db(app)
    compare = AsyncMock()
    monkeypatch.setattr(api.reviewed_comparison, "compare", compare)
    path = "/v1/policy-publications/comparisons"
    assert (
        client.post(path, content='{"items":[],"items":[]}', headers=token(key)).status_code == 422
    )
    assert client.post(path, content=" " * 65_537, headers=token(key)).status_code == 413
    compare.assert_not_awaited()


def test_item_count_is_bounded(setup, monkeypatch):
    app, client, key, _ = setup
    allow_db(app)
    compare = AsyncMock()
    monkeypatch.setattr(api.reviewed_comparison, "compare", compare)
    body = payload()
    for index in range(5):
        item = json.loads(json.dumps(body["items"][0]))
        item["publication_digest"] = str(index) * 64
        body["items"].append(item)
    assert (
        client.post(
            "/v1/policy-publications/comparisons", json=body, headers=token(key)
        ).status_code
        == 422
    )
    compare.assert_not_awaited()
