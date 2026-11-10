"""Deadline worker tests using a synthetic DB boundary, not PostgreSQL evidence."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from app.core.config import Settings
from app.voice.deadlines import mark_expired_provider_calls
from app.voice.service import VoiceSessionService


@pytest.fixture
def context(monkeypatch):
    now = datetime(2026, 11, 7, tzinfo=UTC)
    owner, session_id = uuid.uuid4(), uuid.uuid4()
    ent = SimpleNamespace(user_id=owner, provider="test", reserved_seconds=300, consumed_seconds=0)
    session = SimpleNamespace(
        id=session_id,
        user_id=owner,
        provider="vaani",
        source_mode="synthetic-vaani",
        case_session_id=None,
        state="active",
        expires_at=now - timedelta(seconds=1),
        reserved_seconds=300,
        consumed_seconds=0,
        ended_at=None,
    )
    call = SimpleNamespace(synthetic=True, phase="active")
    locked = []
    statements = []

    class Database:
        def __init__(self, discovery=False):
            self.discovery = discovery
            self.commit = AsyncMock()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def execute(self, statement):
            assert self.discovery
            statements.append(statement)
            return SimpleNamespace(all=lambda: [(session_id, owner)])

        async def scalar(self, statement):
            statements.append(statement)
            sql = str(statement.compile(dialect=postgresql.dialect()))
            assert "FOR UPDATE" in sql
            if "FROM voice_provider_calls" in sql:
                locked.append("binding")
                return values.call
            locked.append("session")
            return values.session

    discovery, mutation = Database(discovery=True), Database()
    queue = [discovery, mutation]

    def factory():
        return queue.pop(0)

    async def lock(db, user_id):
        assert db is mutation and user_id == owner
        locked.append("entitlement")
        return values.ent

    balance = AsyncMock()
    monkeypatch.setattr(VoiceSessionService, "now", AsyncMock(return_value=now))
    monkeypatch.setattr(VoiceSessionService, "lock_entitlement", staticmethod(lock))
    monkeypatch.setattr(VoiceSessionService, "check_balance", balance)
    values = SimpleNamespace(
        ent=ent,
        session=session,
        call=call,
        factory=factory,
        settings=Settings(_env_file=None),
        mutation=mutation,
        queue=queue,
        discovery=discovery,
        locked=locked,
        statements=statements,
        balance=balance,
        now=now,
    )
    return values


@pytest.mark.asyncio
async def test_deadline_only_marks_binding_without_releasing_or_settling(context):
    assert await mark_expired_provider_calls(context.factory, context.settings) == 1
    assert context.call.phase == "termination_required"
    assert context.locked == ["entitlement", "session", "binding"]
    assert context.session.state == "active"
    assert context.session.ended_at is None
    assert context.session.reserved_seconds == context.ent.reserved_seconds == 300
    assert context.session.consumed_seconds == context.ent.consumed_seconds == 0
    context.mutation.commit.assert_awaited_once()
    assert context.balance.await_count == 2
    discovery = str(context.statements[0].compile(dialect=postgresql.dialect()))
    assert "JOIN voice_provider_calls" in discovery
    assert "JOIN voice_entitlements" in discovery
    assert "ORDER BY voice_entitlements.id, voice_sessions.id" in discovery


@pytest.mark.asyncio
async def test_new_worker_pass_does_not_duplicate_existing_durable_marker(context):
    assert await mark_expired_provider_calls(context.factory, context.settings) == 1
    context.queue.extend([context.discovery, context.mutation])
    assert await mark_expired_provider_calls(context.factory, context.settings) == 0
    context.mutation.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["ready", "active", "reconciling"])
@pytest.mark.parametrize("state", ["reserved", "active"])
async def test_open_uncertain_calls_need_termination_without_accounting(context, phase, state):
    context.call.phase = phase
    context.session.state = state
    assert await mark_expired_provider_calls(context.factory, context.settings) == 1
    assert context.session.state == state
    assert context.ent.reserved_seconds == 300


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target", "field", "value"),
    [
        ("ent", "provider", "paid"),
        ("session", "provider", "mock"),
        ("session", "source_mode", "real-policy"),
        ("session", "case_session_id", uuid.uuid4()),
        ("session", "user_id", uuid.uuid4()),
        ("session", "state", "ended"),
        ("session", "state", "failed"),
        ("call", "synthetic", False),
        ("call", "phase", "ended"),
        ("call", "phase", "termination_required"),
    ],
)
async def test_discovery_hints_rechecked_after_locks(context, target, field, value):
    setattr(getattr(context, target), field, value)
    assert await mark_expired_provider_calls(context.factory, context.settings) == 0
    context.mutation.commit.assert_not_awaited()
    context.balance.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["ent", "session", "call"])
async def test_missing_binding_or_owner_never_changes_accounting(context, target):
    setattr(context, target, None)
    assert await mark_expired_provider_calls(context.factory, context.settings) == 0
    context.mutation.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_unexpired_call_is_not_marked(context):
    context.session.expires_at = context.now + timedelta(seconds=1)
    assert await mark_expired_provider_calls(context.factory, context.settings) == 0
    assert context.call.phase == "active"
    context.mutation.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_exact_deadline_is_due(context):
    context.session.expires_at = context.now
    assert await mark_expired_provider_calls(context.factory, context.settings) == 1


@pytest.mark.asyncio
async def test_invalid_balance_fails_closed_and_is_retryable(context):
    context.balance.side_effect = RuntimeError("synthetic invalid balance")
    with pytest.raises(RuntimeError, match="invalid balance"):
        await mark_expired_provider_calls(context.factory, context.settings)
    assert context.call.phase == "active"
    context.mutation.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_commit_does_not_report_success(context):
    context.mutation.commit.side_effect = RuntimeError("synthetic commit failure")
    with pytest.raises(RuntimeError, match="commit failure"):
        await mark_expired_provider_calls(context.factory, context.settings)
    assert context.session.state == "active"
    assert context.ent.reserved_seconds == 300


@pytest.mark.asyncio
async def test_no_discovered_call_does_not_open_mutation_transaction(context):
    async def empty(statement):
        return SimpleNamespace(all=lambda: [])

    context.discovery.execute = empty
    assert await mark_expired_provider_calls(context.factory, context.settings) == 0
    assert context.queue == [context.mutation]
