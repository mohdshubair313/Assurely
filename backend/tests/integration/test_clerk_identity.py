"""Disposable Postgres migration/ownership checks; never a live Clerk account test."""

import asyncio
import os
import runpy
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, insert, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.v1 import consent as consent_api
from app.api.v1 import identity as identity_api
from app.api.v1 import message as message_api
from app.api.v1 import report_release as release_api
from app.api.v1 import sessions as sessions_api
from app.core import security
from app.core.config import Settings
from app.core.consent import CONSENT_VERSION
from app.db import advisor_review, auth_identity
from app.db.policy_review_store import Reviewer, WorkflowError
from app.models.db.auth_identity import AuthEvent, AuthIdentity
from app.models.db.consent_record import ConsentRecord
from app.models.db.escalation import Escalation
from app.models.db.report_release import ReportHead
from app.models.db.session import Session
from app.models.db.user import User
from app.models.db.user_profile_memory import UserProfileMemory
from tests.unit.test_clerk_auth import ISSUER, ORIGIN, bearer, claims

URL = os.environ.get("AUTH_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="Explicit disposable auth database required")
OLD = uuid.UUID("00000000-0000-4000-8000-000000000987")


@pytest.fixture(scope="module")
def database():
    if make_url(URL).database != "assurely_clerk_auth_test":
        raise RuntimeError("Refusing a database other than assurely_clerk_auth_test")
    engine = create_engine(URL, hide_parameters=True)
    migrations = sorted((Path(__file__).parents[2] / "alembic/versions").glob("[0-9]*.py"))
    with engine.begin() as db, Operations.context(MigrationContext.configure(db)):
        for path in migrations:
            if path.name.startswith("010_"):
                db.execute(insert(User).values(id=OLD, role="customer"))
                db.execute(insert(Session).values(id=OLD, user_id=OLD, intent="health"))
                db.execute(
                    text("INSERT INTO consent_records (user_id,scope) VALUES (:id,'save_profile')"),
                    {"id": OLD},
                )
            runpy.run_path(str(path))["upgrade"]()
    async_engine = create_async_engine(
        make_url(URL).set(drivername="postgresql+asyncpg"), poolclass=NullPool, hide_parameters=True
    )
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    yield engine, factory
    engine.dispose()
    asyncio.run(async_engine.dispose())


@pytest.fixture
def context(database, monkeypatch):
    from types import SimpleNamespace

    from cryptography.hazmat.primitives.asymmetric import rsa

    engine, factory = database
    settings = Settings(
        _env_file=None,
        auth_provider="clerk",
        auth_issuer=ISSUER,
        auth_jwks_url=ISSUER + "/.well-known/jwks.json",
        auth_authorized_parties=[ORIGIN],
        database_url=URL,
    )
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    for module in (security, auth_identity, consent_api, message_api, advisor_review, release_api):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(auth_identity, "_engine", lambda _: engine)
    monkeypatch.setattr(
        security,
        "_jwks_client",
        lambda _: SimpleNamespace(
            get_signing_key_from_jwt=lambda _: SimpleNamespace(key=key.public_key())
        ),
    )
    for module in (consent_api, identity_api, message_api, sessions_api, release_api):
        monkeypatch.setattr(module, "AsyncSessionLocal", factory)
    app = FastAPI()
    for router in (
        consent_api.router,
        identity_api.router,
        message_api.router,
        sessions_api.router,
        release_api.router,
    ):
        app.include_router(router, prefix="/v1")
    client = TestClient(app)

    def headers(subject="user_integration123"):
        return {"Authorization": "Bearer " + bearer(key, claims(sub=subject)).credentials}

    return engine, factory, settings, client, headers


def test_migrations_preserve_existing_uuid_and_do_not_relabel_old_consent(database):
    engine, _ = database
    with engine.connect() as db:
        assert db.scalar(select(User.id).where(User.id == OLD)) == OLD
        assert db.scalar(select(Session.user_id).where(Session.id == OLD)) == OLD
        assert (
            db.scalar(select(ConsentRecord.purpose_version).where(ConsentRecord.user_id == OLD))
            == "legacy-v0"
        )
        assert db.scalar(select(func.count()).select_from(AuthIdentity)) == 0


def test_concurrent_first_use_and_restart_keep_one_local_uuid(context):
    engine, _, _, _, _ = context
    with ThreadPoolExecutor(max_workers=6) as pool:
        ids = list(
            pool.map(
                lambda _: auth_identity.resolve_identity(ISSUER, "user_concurrent123"), range(12)
            )
        )
    assert len(set(ids)) == 1
    engine.dispose()
    assert auth_identity.resolve_identity(ISSUER, "user_concurrent123") == ids[0]
    with engine.connect() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuthIdentity)
                .where(AuthIdentity.subject == "user_concurrent123")
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuthEvent)
                .where(AuthEvent.user_id == ids[0], AuthEvent.action == "identity_created")
            )
            == 1
        )


def test_issuer_isolation_and_account_disable(context):
    engine, _, _, _, _ = context
    first = auth_identity.resolve_identity(ISSUER, "user_isolation123")
    other = auth_identity.resolve_identity("https://other.example", "user_isolation123")
    assert first != other and first != OLD
    with engine.begin() as db:
        db.execute(update(AuthIdentity).where(AuthIdentity.user_id == other).values(disabled=True))
    with pytest.raises(HTTPException) as exc:
        auth_identity.resolve_identity("https://other.example", "user_isolation123")
    assert exc.value.status_code == 403


def test_login_is_not_consent_and_current_version_required(context):
    engine, _, _, client, headers = context
    signed = headers()
    owner = client.get("/v1/me", headers=signed).json()["user_id"]
    result = client.get("/v1/me/consents", headers=signed)
    assert result.status_code == 200
    assert not any(row["granted"] for row in result.json()["purposes"])
    body = {"user_id": owner, "scope": "process_comparison", "action": "grant"}
    assert client.post("/v1/consent", headers=signed, json=body).status_code == 422
    body["purpose_version"] = CONSENT_VERSION
    assert client.post("/v1/consent", headers=signed, json=body).status_code == 200
    with engine.connect() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(ConsentRecord)
                .where(
                    ConsentRecord.user_id == uuid.UUID(owner), ConsentRecord.revoked_at.is_(None)
                )
            )
            == 1
        )
    assert (
        client.post("/v1/consent", headers=headers("user_other123"), json=body).status_code == 403
    )
    assert (
        client.delete(f"/v1/profile-memory/{owner}", headers=headers("user_other123")).status_code
        == 403
    )


def test_revoke_blocks_next_processing_and_erases_saved_profile(context, monkeypatch):
    engine, _, _, client, headers = context
    signed = headers()
    owner = client.get("/v1/me", headers=signed).json()["user_id"]

    def forbidden():
        raise AssertionError("Revoked consent reached graph execution")

    monkeypatch.setattr(message_api, "get_app_graph", forbidden)
    for scope in ("save_profile", "process_comparison"):
        grant = {
            "user_id": owner,
            "scope": scope,
            "action": "grant",
            "purpose_version": CONSENT_VERSION,
        }
        assert client.post("/v1/consent", headers=signed, json=grant).status_code == 200
    with engine.begin() as db:
        db.execute(
            insert(UserProfileMemory).values(
                user_id=uuid.UUID(owner), profile_snapshot_json={"synthetic": True}
            )
        )
    for scope in ("save_profile", "process_comparison"):
        assert (
            client.post(
                "/v1/consent",
                headers=signed,
                json={"user_id": owner, "scope": scope, "action": "revoke"},
            ).status_code
            == 200
        )
    with engine.connect() as db:
        assert (
            db.scalar(
                select(UserProfileMemory.user_id).where(
                    UserProfileMemory.user_id == uuid.UUID(owner)
                )
            )
            is None
        )
    response = client.post(
        "/v1/message",
        headers=signed,
        json={"session_id": str(uuid.uuid4()), "user_message": "synthetic question"},
    )
    assert response.status_code == 403
    assert client.post("/v1/message", json={"user_message": "synthetic"}).status_code == 401


@pytest.mark.asyncio
async def test_admin_assignment_is_separate_from_advisor_and_does_not_release(context):
    engine, factory, settings, client, headers = context
    advisor = auth_identity.resolve_identity(ISSUER, "user_advisor123")
    admin = auth_identity.resolve_identity(ISSUER, "user_admin123")
    owner = auth_identity.resolve_identity(ISSUER, "user_owner123")
    settings.advisor_subjects = [str(advisor)]
    settings.admin_subjects = [str(admin)]
    session_id, escalation_id = uuid.uuid4(), uuid.uuid4()
    with engine.begin() as db:
        db.execute(insert(Session).values(id=session_id, user_id=owner))
        db.execute(
            insert(Escalation).values(
                id=escalation_id, session_id=session_id, reason="Synthetic hold", status="pending"
            )
        )
    async with factory() as db, db.begin():
        with pytest.raises(WorkflowError) as exc:
            await advisor_review.require_assignment(db, Reviewer(advisor, ISSUER), session_id)
        assert exc.value.status == 403
    path = f"/v1/admin/escalations/{escalation_id}/assign"
    command = {"advisor_id": str(advisor), "reason": "Synthetic assignment, not approval"}
    assert client.post(path, headers=headers("user_advisor123"), json=command).status_code == 403
    response = client.post(path, headers=headers("user_admin123"), json=command)
    assert response.status_code == 200 and response.json()["delivery_authorized"] is False
    async with factory() as db, db.begin():
        await advisor_review.require_assignment(db, Reviewer(advisor, ISSUER), session_id)
        with pytest.raises(WorkflowError):
            await advisor_review.require_assignment(db, Reviewer(advisor, ISSUER), uuid.uuid4())


def test_auth_audit_is_immutable_and_populated_migration_cannot_downgrade(database):
    engine, _ = database
    with pytest.raises(DBAPIError), engine.begin() as db:
        db.execute(text("DELETE FROM auth_events"))
    migration = Path(__file__).parents[2] / "alembic/versions/010_clerk_identity.py"
    with (
        pytest.raises(DBAPIError),
        engine.begin() as db,
        Operations.context(MigrationContext.configure(db)),
    ):
        runpy.run_path(str(migration))["downgrade"]()


@pytest.mark.asyncio
async def test_stale_graph_consent_cannot_resave_a_revoked_profile(context, monkeypatch):
    from app.graph.nodes import persist_memory
    from app.graph.state import create_initial_state

    engine, factory, settings, _, _ = context
    owner = auth_identity.resolve_identity(ISSUER, "user_revokedgraph123")
    monkeypatch.setattr(persist_memory, "AsyncSessionLocal", factory)
    monkeypatch.setattr(persist_memory, "get_settings", lambda: settings)
    state = create_initial_state(
        session_id=str(uuid.uuid4()),
        user_id=str(owner),
        consent={"granted": True, "scopes": ["save_profile"]},
        user_profile={"synthetic": True},
    )
    result = await persist_memory.persist_memory_node(state)
    assert result["profile_memory_persisted"] is False
    with engine.connect() as db:
        assert (
            db.scalar(select(UserProfileMemory.user_id).where(UserProfileMemory.user_id == owner))
            is None
        )


def test_empty_migration_downgrade_and_upgrade_are_reversible(database):
    engine, _ = database
    migrations = sorted((Path(__file__).parents[2] / "alembic/versions").glob("[0-9]*.py"))
    with engine.connect() as db:
        transaction = db.begin()
        try:
            db.execute(text("CREATE SCHEMA auth_empty_rollback_test"))
            db.execute(text("SET LOCAL search_path TO auth_empty_rollback_test"))
            with Operations.context(MigrationContext.configure(db)):
                for path in migrations:
                    runpy.run_path(str(path))["upgrade"]()
                current = runpy.run_path(str(migrations[-1]))
                current["downgrade"]()
                current["upgrade"]()
            assert db.scalar(text("SELECT count(*) FROM auth_identities")) == 0
        finally:
            transaction.rollback()


def test_clerk_owned_session_restore_and_refresh_cannot_release_a_hold(context, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    engine, _, _, client, headers = context
    signed = headers("user_restore123")
    owner = uuid.UUID(client.get("/v1/me", headers=signed).json()["user_id"])
    session_id, turn = uuid.uuid4(), uuid.uuid4()
    with engine.begin() as db:
        db.execute(insert(Session).values(id=session_id, user_id=owner, intent="health"))
        db.execute(
            insert(ReportHead).values(
                issuer=ISSUER,
                session_id=session_id,
                owner_id=owner,
                turn_id=turn,
                status="running",
                guardrail_approved=False,
            )
        )
    graph = SimpleNamespace(aget_state=AsyncMock(return_value=None))
    monkeypatch.setattr(message_api, "get_app_graph", lambda: graph)
    # No in-process checkpoint after restart: only durable ownership/metadata remains.
    for _ in range(2):
        restored = client.get(f"/v1/session/{session_id}", headers=signed)
        assert restored.status_code == 200 and restored.json()["messages"] == []
        status = client.get(f"/v1/sessions/{session_id}/report-status", headers=signed)
        assert status.status_code == 200 and status.json()["delivery_hold"] is True
        assert "output" not in status.json()
    other = headers("user_wrongowner123")
    assert client.get(f"/v1/session/{session_id}", headers=other).status_code == 403
    assert client.get(f"/v1/sessions/{session_id}/report-status", headers=other).status_code == 403
