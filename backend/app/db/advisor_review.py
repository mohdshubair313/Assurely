"""Durable report-specific advisor review; approval never releases a report alone."""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.correlation import database_session_id
from app.db.policy_review_store import Reviewer, WorkflowError
from app.db.reviewed_delivery import check_reviewed_delivery
from app.db.source_review import ClosedModel
from app.models.db.advisor_review import AdvisorDecision, AdvisorReport
from app.models.db.session import Session


class DecisionCommand(ClosedModel):
    request_key: uuid.UUID
    expected_revision: int = Field(ge=0, strict=True)
    action: Literal["approve", "revoke"]
    reason: str = Field(min_length=1, max_length=2000, strict=True)
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def valid_decision(self) -> DecisionCommand:
        if not self.reason.strip():
            raise ValueError("A reason is required")
        if (self.action == "approve") != (self.expires_at is not None):
            raise ValueError("Only approval requires expiry")
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("Expiry must include timezone")
        return self


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _digest(issuer: str, session: uuid.UUID, owner: uuid.UUID, snapshot: dict[str, Any]) -> str:
    return _hash(
        {
            "version": "advisor-report-v1",
            "issuer": issuer,
            "session_id": str(session),
            "owner_id": str(owner),
            "snapshot": snapshot,
        }
    )


async def _lock(db: AsyncSession, digest: str) -> None:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"advisor-report:{digest}"},
    )


def snapshot_payload(state: dict[str, Any]) -> dict[str, Any]:
    """Only the exact report and its evidence/scenario belong in review storage."""
    result: dict[str, Any] = {key: state[key] for key in (
        "intent", "input_status", "missing_fields", "reviewed_comparison_request", "output",
    ) if key in state}
    draft = state.get("draft_output", {})
    result["draft_output"] = {key: draft[key] for key in ("stage", "reviewed_comparison")
                              if key in draft}
    return copy.deepcopy(result)


async def stage(
    db: AsyncSession,
    actor: Reviewer,
    session_key: str,
    state: dict[str, Any],
) -> dict[str, Any]:
    """Take only server checkpoint content, never a caller-supplied report."""
    session_id = database_session_id(session_key)
    session = await db.get(Session, session_id)
    if session is None or not state.get("user_id"):
        raise WorkflowError(409, "An authenticated session owner is required.")
    owner = uuid.UUID(state["user_id"])
    if session.user_id != owner or state.get("session_id") != session_key:
        raise WorkflowError(409, "Session ownership does not match the report.")
    if actor.subject == owner:
        raise WorkflowError(403, "Independent advisor review is required.")
    # Persist no chat history, free-form profile, model diagnostics or access token.
    snapshot: dict[str, Any] = copy.deepcopy(
        {
            key: state[key]
            for key in (
                "intent",
                "input_status",
                "missing_fields",
                "reviewed_comparison_request",
                "output",
            )
            if key in state
        }
    )
    draft = state.get("draft_output", {})
    snapshot["draft_output"] = {
        key: draft[key] for key in ("stage", "reviewed_comparison") if key in draft
    }
    digest = _digest(actor.issuer, session_id, owner, snapshot)
    # Same order for staging and decisions: report lock, then publication locks.
    await _lock(db, digest)
    check = await check_reviewed_delivery(db, actor.issuer, snapshot)
    if not check.evidence_current:
        raise WorkflowError(409, "Report evidence is not available for advisor review.")
    await db.execute(
        insert(AdvisorReport)
        .values(
            digest=digest,
            issuer=actor.issuer,
            session_id=session_id,
            owner_id=owner,
            snapshot=snapshot,
        )
        .on_conflict_do_nothing(index_elements=[AdvisorReport.digest])
    )
    row = await _row(db, actor, digest)
    return _report(row)


async def _row(db: AsyncSession, actor: Reviewer, digest: str) -> AdvisorReport:
    await _lock(db, digest)
    row = await db.scalar(
        select(AdvisorReport)
        .where(
            AdvisorReport.digest == digest,
            AdvisorReport.issuer == actor.issuer,
        )
        .with_for_update()
    )
    if row is None:
        raise WorkflowError(404, "Advisor report not found.")
    if actor.subject == row.owner_id:
        raise WorkflowError(403, "Independent advisor review is required.")
    if _digest(row.issuer, row.session_id, row.owner_id, row.snapshot) != row.digest:
        raise WorkflowError(409, "Advisor report integrity check failed.")
    session = await db.get(Session, row.session_id)
    if session is None or session.user_id != row.owner_id:
        raise WorkflowError(409, "Report ownership is no longer valid.")
    return row


def _report(row: AdvisorReport) -> dict[str, Any]:
    return {
        "report_digest": row.digest,
        "session_id": str(row.session_id),
        "owner_id": str(row.owner_id),
        "report": copy.deepcopy(row.snapshot["output"]),
        "scenario": copy.deepcopy(row.snapshot["reviewed_comparison_request"]),
        "customer_delivery_authorized": False,
    }


async def _latest(db: AsyncSession, digest: str) -> AdvisorDecision | None:
    return await db.scalar(
        select(AdvisorDecision)
        .where(
            AdvisorDecision.report_digest == digest,
        )
        .order_by(AdvisorDecision.revision.desc())
        .limit(1)
    )


def _receipt(event: AdvisorDecision) -> dict[str, Any]:
    return {
        "event_id": str(event.id),
        "report_digest": event.report_digest,
        "revision": event.revision,
        "action": event.action,
        "expires_at": event.expires_at.isoformat() if event.expires_at else None,
        "scope": "historical_advisor_decision",
        "customer_delivery_authorized": False,
    }


async def read(db: AsyncSession, actor: Reviewer, digest: str) -> dict[str, Any]:
    row = await _row(db, actor, digest)
    event = await _latest(db, digest)
    status = "pending"
    if event:
        status = (
            "revoked"
            if event.action == "revoke"
            else (
                "expired"
                if event.expires_at is None or event.expires_at <= datetime.now(UTC)
                else "approved"
            )
        )
    return {
        **_report(row),
        "review_status": status,
        "revision": event.revision if event else 0,
        "latest_decision": _receipt(event) if event else None,
        "requires_fresh_release_check": True,
    }


async def decide(
    db: AsyncSession,
    actor: Reviewer,
    digest: str,
    command: DecisionCommand,
) -> dict[str, Any]:
    """Serialize revisions and request retries; bind approval to exact stored content."""
    fingerprint = _hash({"digest": digest, "command": command.model_dump(mode="json")})
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {
            "key": f"advisor:{actor.issuer}:{actor.subject}:{command.request_key}",
        },
    )
    row = await _row(db, actor, digest)
    prior = await db.scalar(
        select(AdvisorDecision).where(
            AdvisorDecision.issuer == actor.issuer,
            AdvisorDecision.actor_id == actor.subject,
            AdvisorDecision.request_key == command.request_key,
        )
    )
    if prior:
        if prior.request_hash != fingerprint:
            raise WorkflowError(409, "Request key was used for a different decision.")
        return _receipt(prior)
    latest = await _latest(db, digest)
    revision = latest.revision if latest else 0
    if revision != command.expected_revision:
        raise WorkflowError(409, "Advisor review revision changed.")
    if command.action == "approve":
        check = await check_reviewed_delivery(db, actor.issuer, row.snapshot)
        if not check.evidence_current:
            raise WorkflowError(409, "Report evidence changed or is unavailable.")
        now = datetime.now(UTC)
        expiry = command.expires_at
        assert expiry is not None
        citations = [s["citations"][0] for s in row.snapshot["output"]["sentences"]]
        source_expiry = min(datetime.fromisoformat(c["expires_at"]) for c in citations)
        if not now < expiry <= min(now + timedelta(days=7), source_expiry):
            raise WorkflowError(
                422, "Approval expiry must fit the current evidence and seven days."
            )
    elif latest is None or latest.action != "approve":
        raise WorkflowError(409, "There is no approval to revoke.")
    event = AdvisorDecision(
        id=uuid.uuid4(),
        report_digest=digest,
        issuer=actor.issuer,
        actor_id=actor.subject,
        request_key=command.request_key,
        request_hash=fingerprint,
        revision=revision + 1,
        action=command.action,
        reason=command.reason,
        expires_at=command.expires_at,
    )
    db.add(event)
    await db.flush()
    return _receipt(event)
