"""Serialize current turns, advisor decisions and fresh report release checks."""

from __future__ import annotations

import copy
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.correlation import SESSION_NAMESPACE, database_session_id
from app.db import advisor_review
from app.db.policy_review_store import WorkflowError
from app.db.reviewed_delivery import check_reviewed_delivery
from app.db.source_review import ClosedModel, Digest
from app.models.db.advisor_review import AdvisorReport
from app.models.db.report_release import ReleaseReceipt, ReportHead
from app.models.db.session import Session
from app.models.db.user import User


class ReleaseCommand(ClosedModel):
    request_key: uuid.UUID
    turn_id: uuid.UUID
    report_digest: Digest


async def _lock(db: AsyncSession, issuer: str, session_id: uuid.UUID) -> None:
    if not issuer.strip():
        raise WorkflowError(503, "Report release identity issuer is not configured.")
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"report-head:{issuer}:{session_id}"},
    )


async def head(db: AsyncSession, issuer: str, key: str, owner: uuid.UUID) -> ReportHead:
    session_id = database_session_id(key)
    await _lock(db, issuer, session_id)
    row = await db.get(ReportHead, (issuer, session_id))
    session = await db.get(Session, session_id)
    if row is None or session is None:
        raise WorkflowError(404, "Current report is unavailable.")
    if row.owner_id != owner or session.user_id != owner:
        raise WorkflowError(403, "This session belongs to another user.")
    return row


async def begin_turn(
    db: AsyncSession,
    issuer: str,
    key: str,
    owner: uuid.UUID | None,
) -> uuid.UUID:
    """Commit this invalidation before entering the graph, including rejected turns."""
    session_id = database_session_id(key)
    owner = owner or uuid.uuid5(SESSION_NAMESPACE, f"user:{session_id}")
    await _lock(db, issuer, session_id)
    await db.execute(insert(User).values(id=owner, role="customer").on_conflict_do_nothing())
    await db.execute(insert(Session).values(id=session_id, user_id=owner).on_conflict_do_nothing())
    session = await db.get(Session, session_id)
    if session is None or session.user_id != owner:
        raise WorkflowError(403, "This session belongs to another user.")
    row = await db.get(ReportHead, (issuer, session_id))
    if row is not None and row.status == "running":
        raise WorkflowError(409, "A turn is already running for this session.")
    turn_id = uuid.uuid4()
    if row is None:
        row = ReportHead(issuer=issuer, session_id=session_id, owner_id=owner)
        db.add(row)
    row.turn_id, row.status, row.report_digest = turn_id, "running", None
    row.guardrail_approved = False
    await db.flush()
    return turn_id


async def finish_turn(
    db: AsyncSession,
    issuer: str,
    key: str,
    turn_id: uuid.UUID,
    state: dict[str, Any] | None,
) -> None:
    session_id = database_session_id(key)
    await _lock(db, issuer, session_id)
    row = await db.get(ReportHead, (issuer, session_id))
    if row is None or row.turn_id != turn_id or row.status != "running":
        raise WorkflowError(409, "The current turn changed.")
    row.status = "failed" if state is None else "complete"
    if (
        state is None
        or state.get("input_status") != "accepted"
        or state.get("user_id") != str(row.owner_id)
        or state.get("session_id") != key
        or state.get("intent") != "health"
        or state.get("missing_fields")
    ):
        return
    snapshot = advisor_review.snapshot_payload(state)
    digest = advisor_review._digest(issuer, session_id, row.owner_id, snapshot)
    await advisor_review._lock(db, digest)
    check = await check_reviewed_delivery(db, issuer, snapshot)
    if not check.evidence_current:
        return
    await db.execute(
        insert(AdvisorReport)
        .values(
            digest=digest,
            issuer=issuer,
            session_id=session_id,
            owner_id=row.owner_id,
            snapshot=snapshot,
        )
        .on_conflict_do_nothing()
    )
    row.report_digest = digest
    # Only guardrail sets this on the server. Advisor approval cannot replace it.
    row.guardrail_approved = state.get("approved") is True


async def release(
    db: AsyncSession,
    issuer: str,
    key: str,
    owner: uuid.UUID,
    command: ReleaseCommand,
    advisor_subjects: set[uuid.UUID],
) -> dict[str, Any]:
    """Return original output only after a receipt is flushed in the same transaction.

    Caller must commit before sending any response. Every retry revalidates live
    authority; a receipt proves a decision, never network delivery or future access.
    Lock order: request key, session head, advisor report, publication scope.
    """
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"release:{issuer}:{owner}:{command.request_key}"},
    )
    current = await head(db, issuer, key, owner)
    if (
        current.status != "complete"
        or current.turn_id != command.turn_id
        or current.report_digest != command.report_digest
        or not current.guardrail_approved
    ):
        raise WorkflowError(409, "Current report is not approved for release.")
    await advisor_review._lock(db, command.report_digest)
    report = await db.get(AdvisorReport, command.report_digest)
    if (
        report is None
        or report.issuer != issuer
        or report.owner_id != owner
        or report.session_id != current.session_id
        or advisor_review._digest(issuer, current.session_id, owner, report.snapshot)
        != report.digest
    ):
        raise WorkflowError(409, "Report integrity check failed.")
    event = await advisor_review._latest(db, report.digest)
    if (
        event is None
        or event.issuer != issuer
        or event.action != "approve"
        or event.actor_id == owner
        or event.actor_id not in advisor_subjects
        or event.expires_at is None
        or event.expires_at <= datetime.now(UTC)
    ):
        raise WorkflowError(409, "Current advisor approval is required.")
    check = await check_reviewed_delivery(db, issuer, report.snapshot)
    if not check.evidence_current or event.expires_at <= datetime.now(UTC):
        raise WorkflowError(409, "Report evidence or advisor approval is no longer current.")
    prior = await db.scalar(
        select(ReleaseReceipt).where(
            ReleaseReceipt.issuer == issuer,
            ReleaseReceipt.owner_id == owner,
            ReleaseReceipt.request_key == command.request_key,
        )
    )
    if prior is not None:
        if (
            prior.session_id != current.session_id
            or prior.turn_id != command.turn_id
            or prior.report_digest != report.digest
            or prior.advisor_event_id != event.id
        ):
            raise WorkflowError(409, "Release request key was used for another decision.")
        receipt = prior
    else:
        receipt = ReleaseReceipt(
            id=uuid.uuid4(),
            issuer=issuer,
            session_id=current.session_id,
            owner_id=owner,
            turn_id=command.turn_id,
            report_digest=report.digest,
            advisor_event_id=event.id,
            request_key=command.request_key,
            created_at=datetime.now(UTC),
        )
        db.add(receipt)
        await db.flush()
    now = datetime.now(UTC)
    evidence_expiry = min(
        datetime.fromisoformat(s["citations"][0]["expires_at"])
        for s in report.snapshot["output"]["sentences"]
    )
    if event.expires_at <= now or evidence_expiry <= now:
        raise WorkflowError(409, "Approval expired before the release decision completed.")
    return {
        "delivery_hold": False,
        "output": copy.deepcopy(report.snapshot["output"]),
        "release_receipt": {
            "id": str(receipt.id),
            "report_digest": report.digest,
            "turn_id": str(current.turn_id),
            "advisor_event_id": str(event.id),
            "scope": "transaction_time_release_decision",
        },
    }
