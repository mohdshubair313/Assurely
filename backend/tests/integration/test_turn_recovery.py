"""Fencing, owner recovery and reconnect persistence in disposable Postgres."""

import runpy
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.db import report_release, turn_recovery
from app.db.policy_review_store import WorkflowError
from app.graph import runtime
from app.models.db.report_release import ReportHead, TurnRecoveryReceipt
from tests.integration.test_policy_review_workflow import ACTOR, URL
from tests.integration.test_reviewed_policy_terms import database as _database
from tests.unit.test_policy_review_api import SUBJECT, setup, token

database = _database
pytestmark = pytest.mark.skipif(not URL, reason="Isolated policy-review Postgres required")


@pytest.fixture
def configured(database, monkeypatch):
    _, factory, _ = database
    settings = SimpleNamespace(environment="production", auth_issuer=ACTOR.issuer,
                               database_url=URL)
    monkeypatch.setattr(turn_recovery, "get_settings", lambda: settings)
    monkeypatch.setattr(turn_recovery, "AsyncSessionLocal", factory)
    monkeypatch.setattr(runtime, "get_settings", lambda: settings)
    monkeypatch.setattr(runtime, "AsyncSessionLocal", factory)
    return factory


async def start(factory, key, owner):
    async with factory() as db, db.begin():
        return await report_release.begin_turn(db, ACTOR.issuer, key, owner)


async def recover(factory, key, owner, command):
    async with turn_recovery.execution_guard(ACTOR.issuer, key), factory() as db, db.begin():
        return await turn_recovery.recover(db, ACTOR.issuer, key, owner, command)


async def test_live_worker_blocks_recovery_or_parallel_execution(configured):
    factory = configured
    key, owner = str(uuid.uuid4()), uuid.uuid4()
    turn = await start(factory, key, owner)
    command = turn_recovery.RecoveryCommand(turn_id=turn, request_key=uuid.uuid4())
    async with turn_recovery.execution_guard(ACTOR.issuer, key):
        with pytest.raises(WorkflowError, match="being processed"):
            await recover(factory, key, owner, command)
    receipt = await recover(factory, key, owner, command)
    assert receipt["delivery_hold"] and receipt["historical_receipt"]
    assert await recover(factory, key, owner, command) == receipt
    async with factory() as db:
        row = await db.get(ReportHead, (ACTOR.issuer, uuid.UUID(key)))
        assert row.status == "failed" and row.report_digest is None
        assert not row.guardrail_approved
    with pytest.raises(DBAPIError, match="append-only"):
        async with factory() as db, db.begin():
            await db.execute(text("DELETE FROM turn_recovery_receipts"))


async def test_recovery_ownership_exact_turn_idempotency_and_late_completion(configured):
    factory = configured
    key, owner = str(uuid.uuid4()), uuid.uuid4()
    first = await start(factory, key, owner)
    command = turn_recovery.RecoveryCommand(turn_id=first, request_key=uuid.uuid4())
    with pytest.raises(WorkflowError) as foreign:
        await recover(factory, key, uuid.uuid4(), command)
    assert foreign.value.status == 403
    with pytest.raises(WorkflowError):
        await recover(factory, key, owner, command.model_copy(update={"turn_id": uuid.uuid4()}))
    receipt = await recover(factory, key, owner, command)
    second = await start(factory, key, owner)
    assert await recover(factory, key, owner, command) == receipt
    async with factory() as db, db.begin():
        with pytest.raises(WorkflowError, match="changed"):
            await report_release.finish_turn(db, ACTOR.issuer, key, first, {})
    async with factory() as db:
        row = await db.get(ReportHead, (ACTOR.issuer, uuid.UUID(key)))
        assert row.status == "running" and row.turn_id == second
        assert len((await db.scalars(select(TurnRecoveryReceipt))).all()) == 1


async def test_checkpoint_survives_pool_recreation_and_turn_namespace_is_fenced(
    configured, monkeypatch,
):
    factory = configured

    def sample_graph(saver):
        graph = StateGraph(dict)
        graph.add_node("record", lambda state: {**state, "recorded": True})
        graph.add_edge(START, "record")
        graph.add_edge("record", END)
        return graph.compile(checkpointer=saver)

    monkeypatch.setattr(runtime, "build_graph", sample_graph)
    key, owner = str(uuid.uuid4()), uuid.uuid4()
    turn = await start(factory, key, owner)
    config = runtime.turn_config(ACTOR.issuer, key, turn)
    async with runtime.durable_graph(setup=True) as graph:
        result = await graph.ainvoke({"session_id": key, "messages": [{"content": "synthetic"}]},
                                    config=config, durability="sync")
        assert result["recorded"]
    # New saver, pool and compiled graph: no process-local state is reused.
    async with runtime.durable_graph() as graph:
        snapshot = await graph.aget_state(config)
        assert snapshot.values == result and not snapshot.next
        assert not (await graph.aget_state(runtime.turn_config(
            "https://other-issuer.test", key, turn))).values
        async with factory() as db, db.begin():
            await report_release.finish_turn(db, ACTOR.issuer, key, turn, result)
        assert await runtime.read_config(key) == config
        second = await start(factory, key, owner)
        # Readers keep the completed turn while the next one is in progress.
        assert await runtime.read_config(key) == config
        assert await runtime.read_config(key, current_only=True) is None
        other = runtime.turn_config(ACTOR.issuer, key, second)
        assert not (await graph.aget_state(other)).values
        # A late abandoned worker can write only its own obsolete namespace.
        await graph.ainvoke({"obsolete": True}, config=config, durability="sync")
        assert not (await graph.aget_state(other)).values


async def test_full_application_graph_checkpoints_json_state_across_reconstruction(
    configured, monkeypatch,
):
    import importlib

    module = importlib.import_module("app.graph.build_graph")
    updates = {
        "input_validate_node": {"input_status": "accepted"},
        "needs_intake_node": {"missing_fields": []},
        "intent_router_node": {"intent": "health"},
        "health_domain_agent_node": {"retrieved_facts": []},
        "risk_analysis_node": {"calculator_outputs": {}},
        "compare_verify_node": {"draft_output": {}},
        "guardrail_node": {"approved": False, "escalation": True},
        "explanation_report_node": {"output": {}},
        "escalate_node": {"delivery_hold": True},
        "persist_memory_node": {},
    }
    for name, value in updates.items():
        async def node(state, result=value):
            return result
        monkeypatch.setattr(module, name, node)
    config = runtime.turn_config(ACTOR.issuer, str(uuid.uuid4()), uuid.uuid4())
    initial = {"messages": [{"role": "user", "content": "Synthetic health question"}],
               "user_profile": {"age": 35}, "session_id": "synthetic-full-graph"}
    async with runtime.durable_graph(setup=True) as graph:
        result = await graph.ainvoke(initial, config=config, durability="sync")
        assert result["delivery_hold"] is True
        history = [snapshot async for snapshot in graph.aget_state_history(config)]
        assert len(history) >= 10
    async with runtime.durable_graph() as graph:
        snapshot = await graph.aget_state(config)
        assert snapshot.values == result and not snapshot.next


async def test_startup_refuses_missing_checkpoint_schema(configured):
    with pytest.raises(Exception, match="checkpoint_migrations"):
        async with runtime.durable_graph():
            pytest.fail("Missing schema must not fall back to memory")


@pytest.mark.parametrize("record", ["recovery", "completion"])
async def test_recovery_migration_empty_roundtrip_and_populated_refusal(
    configured, database, record,
):
    engine, factory, _ = database
    migration = runpy.run_path(str(
        Path(__file__).parents[2] / "alembic/versions/009_turn_recovery.py"
    ))

    def run(conn, action):
        with Operations.context(MigrationContext.configure(conn)):
            migration[action]()

    async with engine.begin() as conn:
        await conn.run_sync(run, "downgrade")
        await conn.run_sync(run, "upgrade")
    key, owner = str(uuid.uuid4()), uuid.uuid4()
    turn = await start(factory, key, owner)
    if record == "recovery":
        await recover(factory, key, owner, turn_recovery.RecoveryCommand(
            turn_id=turn, request_key=uuid.uuid4(),
        ))
    else:
        async with factory() as db, db.begin():
            await report_release.finish_turn(
                db, ACTOR.issuer, key, turn, {"input_status": "rejected"},
            )
    with pytest.raises(DBAPIError, match="Refusing downgrade"):
        async with engine.begin() as conn:
            await conn.run_sync(run, "downgrade")


async def test_failed_recovery_transaction_leaves_running_turn_and_no_receipt(configured):
    factory = configured
    key, owner = str(uuid.uuid4()), uuid.uuid4()
    turn = await start(factory, key, owner)
    async with turn_recovery.execution_guard(ACTOR.issuer, key):
        with pytest.raises(RuntimeError, match="rollback"):
            async with factory() as db, db.begin():
                await turn_recovery.recover(db, ACTOR.issuer, key, owner,
                    turn_recovery.RecoveryCommand(turn_id=turn, request_key=uuid.uuid4()))
                raise RuntimeError("synthetic rollback")
    async with factory() as db:
        row = await db.get(ReportHead, (ACTOR.issuer, uuid.UUID(key)))
        assert row.status == "running"
        assert not (await db.scalars(select(TurnRecoveryReceipt))).all()


async def test_signed_recovery_http_rejects_foreign_owner_and_live_worker(configured, monkeypatch):
    from app.api.v1 import report_release as api

    factory = configured
    app, _, key, settings = setup.__wrapped__(monkeypatch)
    settings.auth_issuer, settings.environment = ACTOR.issuer, "production"
    app.include_router(api.router, prefix="/v1")
    monkeypatch.setattr(api, "get_settings", lambda: settings)
    monkeypatch.setattr(api, "AsyncSessionLocal", factory)
    session_id = str(uuid.uuid4())
    turn = await start(factory, session_id, SUBJECT)
    body = {"turn_id": str(turn), "request_key": str(uuid.uuid4())}
    headers = token(key, iss=ACTOR.issuer)
    path = f"/v1/sessions/{session_id}/recover-turn"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test",
    ) as client:
        assert (await client.post(path, json=body)).status_code == 401
        foreign = token(key, iss=ACTOR.issuer, sub=str(uuid.uuid4()))
        assert (await client.post(path, json=body, headers=foreign)).status_code == 403
        async with turn_recovery.execution_guard(ACTOR.issuer, session_id):
            assert (await client.post(path, json=body, headers=headers)).status_code == 409
        result = await client.post(path, json=body, headers=headers)
        assert result.status_code == 200 and result.json()["delivery_hold"]
        assert (await client.post(path, json=body, headers=headers)).json() == result.json()


async def test_signed_message_continues_from_durable_state_after_runtime_recreation(
    configured, monkeypatch,
):
    from app.api.v1 import message

    factory = configured
    app, _, key, settings = setup.__wrapped__(monkeypatch)
    settings.auth_issuer, settings.environment = ACTOR.issuer, "production"
    app.include_router(message.router, prefix="/v1")
    monkeypatch.setattr(message, "get_settings", lambda: settings)
    monkeypatch.setattr(message, "AsyncSessionLocal", factory)

    def sample_graph(saver):
        graph = StateGraph(dict)
        graph.add_node("record", lambda state: {
            **state, "input_status": "rejected", "user_profile": {"age": 35},
        })
        graph.add_edge(START, "record")
        graph.add_edge("record", END)
        return graph.compile(checkpointer=saver)

    monkeypatch.setattr(runtime, "build_graph", sample_graph)
    session_id = str(uuid.uuid4())
    headers = token(key, iss=ACTOR.issuer)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test",
    ) as client:
        async with runtime.durable_graph(setup=True) as graph:
            monkeypatch.setattr(message, "_production_graph", graph)
            result = await client.post("/v1/message", headers=headers, json={
                "session_id": session_id, "user_message": "First synthetic question",
            })
            assert result.status_code == 200, result.text
            previous = await runtime.read_config(session_id)
        async with runtime.durable_graph() as graph:
            monkeypatch.setattr(message, "_production_graph", graph)
            result = await client.post("/v1/message", headers=headers, json={
                "session_id": session_id, "user_message": "Second synthetic question",
            })
            assert result.status_code == 200, result.text
            current = await runtime.read_config(session_id)
            assert current != previous
            snapshot = await graph.aget_state(current)
            assert len(snapshot.values["messages"]) == 2
            assert snapshot.values["user_profile"] == {"age": 35}
            assert snapshot.values["reviewed_comparison_request"] is None
