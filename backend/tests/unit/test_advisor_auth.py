"""Advisor APIs require verified identity and a distinct explicit allowlist."""

from unittest.mock import AsyncMock

import pytest

from app.api.v1 import advisor_reviews as api
from app.api.v1.policy_reviews import review_db
from app.core import advisor_auth
from tests.unit.test_policy_review_api import DIGEST, SUBJECT, token
from tests.unit.test_policy_review_api import setup as _setup

setup = _setup


@pytest.mark.parametrize(
    "path,method",
    [
        ("/sessions/example/snapshot", "POST"),
        ("/" + DIGEST, "GET"),
        ("/" + DIGEST + "/decisions", "POST"),
    ],
)
def test_advisor_endpoints_reject_missing_identity_and_spoofed_role(
    setup, monkeypatch, path, method
):
    app, client, key, settings = setup
    settings.advisor_subjects = []
    monkeypatch.setattr(advisor_auth, "get_settings", lambda: settings)
    app.include_router(api.router, prefix="/v1")
    assert client.request(method, "/v1/advisor-reviews" + path).status_code == 401
    response = client.request(
        method, "/v1/advisor-reviews" + path, headers=token(key, role="advisor")
    )
    assert response.status_code == 503
    settings.advisor_subjects = ["00000000-0000-4000-8000-000000000999"]
    assert (
        client.request(
            method, "/v1/advisor-reviews" + path, headers=token(key, role="advisor")
        ).status_code
        == 403
    )


def test_decision_body_rejects_forged_identity_and_duplicate_keys(setup, monkeypatch):
    app, client, key, settings = setup
    settings.advisor_subjects = [str(SUBJECT)]
    monkeypatch.setattr(advisor_auth, "get_settings", lambda: settings)
    app.include_router(api.router, prefix="/v1")

    async def db():
        yield AsyncMock()

    app.dependency_overrides[review_db] = db
    store = AsyncMock()
    monkeypatch.setattr(api.store, "decide", store)
    for body in (
        '{"action":"approve","action":"revoke"}',
        '{"actor_id":"forged","action":"approve"}',
    ):
        response = client.post(
            "/v1/advisor-reviews/" + DIGEST + "/decisions",
            headers={**token(key), "Content-Type": "application/json"},
            content=body,
        )
        assert response.status_code == 422
    store.assert_not_awaited()
