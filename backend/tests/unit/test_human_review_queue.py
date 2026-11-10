"""Private operator queue authorization/projection; no provider or notification test."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app.api.v1 import human_review_queue as api
from app.api.v1.policy_reviews import review_db
from app.core import security
from app.core.config import Settings
from app.db.human_review_queue import queue_query, read_queue
from app.db.policy_review_store import WorkflowError

ISSUER = "https://queue.synthetic.test"
ADMIN = uuid.UUID("00000000-0000-4000-8000-000000000591")
CUSTOMER = uuid.UUID("00000000-0000-4000-8000-000000000592")
REVIEWER = uuid.UUID("00000000-0000-4000-8000-000000000593")


def client(monkeypatch, subject=ADMIN, *, test_admin=False, provider="clerk"):
    settings = Settings(
        _env_file=None,
        auth_provider=provider,
        auth_issuer=ISSUER,
        auth_jwks_url=f"{ISSUER}/.well-known/jwks.json",
        auth_authorized_parties=["http://localhost:3000"],
        auth_audience="synthetic-queue",
        admin_subjects=[str(ADMIN)],
        policy_reviewer_subjects=[str(REVIEWER)],
        auth_test_subjects=[str(ADMIN)] if test_admin else [],
    )
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    app = FastAPI()
    app.include_router(api.router)
    if subject is not None:
        app.dependency_overrides[security.require_authenticated_user_id] = lambda: subject

    async def database():
        yield object()

    app.dependency_overrides[review_db] = database
    read = AsyncMock(
        return_value={
            "items": [],
            "truncated": False,
            "pagination": "first_page_only",
            "notification_confirmed": False,
            "delivery_authorized": False,
        }
    )
    monkeypatch.setattr(api, "read_queue", read)
    return TestClient(app), read


@pytest.mark.parametrize("subject", [None, CUSTOMER, REVIEWER])
def test_operator_queue_rejects_unauthenticated_and_non_admin(monkeypatch, subject):
    http, read = client(monkeypatch, subject)
    assert http.get("/admin/human-review-queue").status_code == (401 if subject is None else 403)
    read.assert_not_awaited()


def test_operator_queue_test_admin_has_no_authority(monkeypatch):
    http, read = client(monkeypatch, test_admin=True)
    assert http.get("/admin/human-review-queue").status_code == 403
    read.assert_not_awaited()


def test_operator_queue_requires_clerk(monkeypatch):
    http, read = client(monkeypatch, provider="legacy_oidc")
    assert http.get("/admin/human-review-queue").status_code == 503
    read.assert_not_awaited()


@pytest.mark.parametrize("limit", ["0", "101", "-1", "true", "NaN", "10000000000"])
def test_operator_queue_rejects_unbounded_limits(monkeypatch, limit):
    http, read = client(monkeypatch)
    assert http.get(f"/admin/human-review-queue?limit={limit}").status_code == 422
    read.assert_not_awaited()


@pytest.mark.parametrize("limit", [None, 1, 100])
def test_operator_queue_admin_and_default_bound(monkeypatch, limit):
    http, read = client(monkeypatch)
    query = "" if limit is None else f"?limit={limit}"
    response = http.get(f"/admin/human-review-queue{query}")
    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "truncated": False,
        "pagination": "first_page_only",
        "notification_confirmed": False,
        "delivery_authorized": False,
    }
    assert read.await_args.args[1:] == (ISSUER, 25 if limit is None else limit)


def test_operator_queue_missing_schema_is_safe_503(monkeypatch):
    http, read = client(monkeypatch)
    read.side_effect = WorkflowError(503, "Human review queue storage is unavailable.")
    assert http.get("/admin/human-review-queue").json() == {
        "detail": "Human review queue storage is unavailable."
    }
    assert http.get("/admin/human-review-queue").status_code == 503


@pytest.mark.parametrize("limit", [0, 101, -1, True])
def test_store_bound_applies_outside_http(limit):
    with pytest.raises(WorkflowError) as error:
        queue_query(ISSUER, limit)
    assert error.value.status == 422


def test_queue_query_binds_issuer_checks_owner_and_projects_no_content():
    query = queue_query(ISSUER, 25)
    compiled = query.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert ISSUER not in sql
    assert ISSUER in compiled.params.values()
    assert list(query.selected_columns.keys()) == [
        "escalation_id",
        "session_id",
        "request_id",
        "requested_at",
        "status",
    ]
    assert "sessions.user_id = human_review_requests.owner_id" in sql
    assert "escalations.session_id = human_review_requests.session_id" in sql
    assert "PARTITION BY human_review_requests.escalation_id" in sql
    assert "reason" not in sql and "assigned_advisor" not in sql
    assert ["pending", "assigned", "in_review"] in compiled.params.values()
    assert 26 in compiled.params.values()


def test_queue_response_rejects_private_or_approval_fields():
    with pytest.raises(ValidationError):
        api.QueueItem(
            escalation_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            requested_at=datetime.now(UTC),
            status="pending",
            reason="Private content",
        )
    with pytest.raises(ValidationError):
        api.QueuePage(
            items=[],
            truncated=False,
            pagination="first_page_only",
            notification_confirmed=True,
            delivery_authorized=False,
        )


@pytest.mark.asyncio
async def test_store_missing_schema_does_not_query_request_rows():
    database = SimpleNamespace(scalar=AsyncMock(return_value=None), execute=AsyncMock())
    with pytest.raises(WorkflowError) as error:
        await read_queue(database, ISSUER)
    assert error.value.status == 503
    database.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_queue_truncates_explicitly_without_notification_claim():
    rows = [
        {
            "escalation_id": uuid.uuid4(),
            "session_id": uuid.uuid4(),
            "request_id": uuid.uuid4(),
            "requested_at": datetime.now(UTC),
            "status": "pending",
        }
        for _ in range(2)
    ]
    result = SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))
    database = SimpleNamespace(
        scalar=AsyncMock(return_value="human_review_requests"),
        execute=AsyncMock(return_value=result),
    )
    page = await read_queue(database, ISSUER, 1)
    assert page["items"] == rows[:1]
    assert page["truncated"] is True
    assert page["delivery_authorized"] is False
    assert page["notification_confirmed"] is False
