"""Actual guardrail and release transactions using synthetic reviewed policy data."""

import uuid
from types import SimpleNamespace

import pytest

from app.db import report_release
from app.db.policy_review_store import WorkflowError
from app.graph import reviewed_guardrail
from app.graph.nodes import compare_verify, explanation_report, guardrail
from tests.integration.test_advisor_review import approval, decide, prepare, stage
from tests.integration.test_policy_publication_workflow import decide as publication_decide
from tests.integration.test_policy_review_workflow import ACTOR, URL
from tests.integration.test_report_release import release
from tests.integration.test_reviewed_policy_terms import database as _database
from tests.unit.test_policy_publication import publication_input as _publication_input

database = _database
publication_input = _publication_input
pytestmark = pytest.mark.skipif(not URL, reason="Isolated policy-review Postgres required")


async def checked_state(factory, publication_input, monkeypatch):
    state, digest, command = await prepare(factory, publication_input)
    settings = SimpleNamespace(environment="production", auth_issuer=ACTOR.issuer)
    monkeypatch.setattr(compare_verify, "get_settings", lambda: settings)
    monkeypatch.setattr(compare_verify, "AsyncSessionLocal", factory)
    monkeypatch.setattr(guardrail, "get_settings", lambda: settings)
    monkeypatch.setattr(reviewed_guardrail, "AsyncSessionLocal", factory)
    state.update(await compare_verify.compare_verify_node(state))
    state.update(await guardrail.guardrail_node(state))
    assert state["approved"] is True and state["escalation"] is True
    state.update(await explanation_report.explanation_report_node(state))
    assert state["output"]["report_status"] == "reviewed_report_held"
    return state, digest, command


async def bound_report(factory, state):
    owner = uuid.UUID(state["user_id"])
    async with factory() as db, db.begin():
        turn = await report_release.begin_turn(db, ACTOR.issuer, state["session_id"], owner)
    async with factory() as db, db.begin():
        await report_release.finish_turn(db, ACTOR.issuer, state["session_id"], turn, state)
    digest = (await stage(factory, state))["report_digest"]
    command = report_release.ReleaseCommand(
        request_key=uuid.uuid4(), turn_id=turn, report_digest=digest,
    )
    return owner, command


async def test_real_guardrail_requires_advisor_before_transactional_release(
    database, publication_input, monkeypatch,
):
    _, factory, _ = database
    state, _, _ = await checked_state(factory, publication_input, monkeypatch)
    owner, command = await bound_report(factory, state)
    with pytest.raises(WorkflowError):
        await release(factory, state, owner, command)
    await decide(factory, command.report_digest, approval())
    result = await release(factory, state, owner, command)
    assert result["delivery_hold"] is False
    assert result["output"] == state["output"]


async def test_revocation_after_guardrail_blocks_release_and_repeat_approval(
    database, publication_input, monkeypatch,
):
    _, factory, _ = database
    state, publication_digest, publication_command = await checked_state(
        factory, publication_input, monkeypatch,
    )
    owner, command = await bound_report(factory, state)
    await decide(factory, command.report_digest, approval())
    await publication_decide(factory, publication_digest, publication_command.model_copy(update={
        "request_key": uuid.uuid4(), "expected_revision": 1, "action": "revoke",
        "expires_at": None,
    }))
    with pytest.raises(WorkflowError):
        await release(factory, state, owner, command)
    result = await guardrail.guardrail_node(state)
    assert result["approved"] is False and result["escalation"] is True
