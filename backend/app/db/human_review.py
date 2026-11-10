"""Owner-requested human review, independent of voice billing and AI approval.

Lock order for creation: request key, owner budget, report head, escalation row.
Release takes the same report-head lock before checking request chronology.
Requests never change graph output, assignments, or recorded advisor decisions.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db import advisor_review, report_release
from app.db.policy_review_store import WorkflowError
from app.db.source_review import ClosedModel
from app.models.db.escalation import Escalation
from app.models.db.human_review import HumanReviewRequest
from app.models.db.report_release import ReportHead
from app.models.db.session import Session

CASE_REQUEST_LIMIT = 3
OWNER_REQUEST_LIMIT = 20


class RequestCommand(ClosedModel):
    request_key: uuid.UUID


async def available(db: AsyncSession) -> bool:
    exists = await db.scalar(text("SELECT to_regclass('human_review_requests') IS NOT NULL"))
    if not exists and get_settings().human_review_requests_enabled:
        raise WorkflowError(503, "Human review storage is unavailable.")
    return bool(exists)


async def _owned(db: AsyncSession, issuer: str, session_id: uuid.UUID, owner: uuid.UUID) -> None:
    await report_release._lock(db, issuer, session_id)
    case = await db.get(Session, session_id)
    if case is None:
        raise WorkflowError(404, "This case is unavailable.")
    if case.user_id != owner:
        raise WorkflowError(403, "This session belongs to another user.")


async def _latest(
    db: AsyncSession,
    issuer: str,
    session_id: uuid.UUID,
    owner: uuid.UUID,
) -> HumanReviewRequest | None:
    return await db.scalar(
        select(HumanReviewRequest)
        .where(
            HumanReviewRequest.issuer == issuer,
            HumanReviewRequest.session_id == session_id,
            HumanReviewRequest.owner_id == owner,
        )
        .order_by(HumanReviewRequest.requested_at.desc(), HumanReviewRequest.id.desc())
        .limit(1)
    )


async def enforce_fresh_decision(
    db: AsyncSession,
    issuer: str,
    session_id: uuid.UUID,
    owner: uuid.UUID,
    decision_at: datetime,
) -> None:
    """Enforce persisted holds even after disabling creation. Caller holds head lock."""
    if not await available(db):
        return
    row = await _latest(db, issuer, session_id, owner)
    if row is not None and decision_at <= row.requested_at:
        raise WorkflowError(409, "A new human advisor decision is required for this request.")


async def _view(db: AsyncSession, row: HumanReviewRequest) -> dict[str, Any]:
    assignment = await db.get(Escalation, row.escalation_id)
    status = "pending"
    if assignment is not None and assignment.status in {"assigned", "in_review"}:
        status = assignment.status
    # This is only a historical queue status. It never returns report output,
    # private reasons, human identity, or a claim of current release authority.
    head = await db.get(ReportHead, (row.issuer, row.session_id))
    if head is not None and head.status == "complete" and head.report_digest:
        event = await advisor_review._latest(db, head.report_digest)
        settings = get_settings()
        authorized = set(settings.advisor_subjects) - set(settings.auth_test_subjects)
        if (
            event is not None
            and event.issuer == row.issuer
            and event.created_at > row.requested_at
            and event.actor_id != row.owner_id
            and str(event.actor_id) in authorized
            and event.action == "approve"
            and event.expires_at is not None
            and event.expires_at > datetime.now(UTC)
            and assignment is not None
            and assignment.assigned_advisor == event.actor_id
            and assignment.status in {"assigned", "in_review"}
        ):
            status = "decision_recorded"
    return {
        "request_id": str(row.id),
        "session_id": str(row.session_id),
        "status": status,
        "delivery_hold": True,
        "human_connected": False,
        "notification_dispatched": False,
        "requested_at": row.requested_at.isoformat(),
    }


async def read(
    db: AsyncSession,
    issuer: str,
    session_id: uuid.UUID,
    owner: uuid.UUID,
) -> dict[str, Any]:
    await _owned(db, issuer, session_id, owner)
    row = await _latest(db, issuer, session_id, owner) if await available(db) else None
    return {"request": await _view(db, row) if row is not None else None}


async def create(
    db: AsyncSession,
    issuer: str,
    session_id: uuid.UUID,
    owner: uuid.UUID,
    command: RequestCommand,
) -> dict[str, Any]:
    settings = get_settings()
    if (
        not settings.human_review_requests_enabled
        or settings.auth_provider != "clerk"
        or settings.environment not in {"staging", "production"}
        or not issuer.strip()
        or issuer != settings.auth_issuer
    ):
        raise WorkflowError(503, "Human review requests are not enabled.")
    for key in (
        f"human-review-request:{issuer}:{owner}:{command.request_key}",
        f"human-review-owner:{issuer}:{owner}",
    ):
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key}
        )
    await _owned(db, issuer, session_id, owner)
    await available(db)
    digest = hashlib.sha256(
        json.dumps(
            {
                "version": "human-review-request-v1",
                "issuer": issuer,
                "owner_id": str(owner),
                "session_id": str(session_id),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    prior = await db.scalar(
        select(HumanReviewRequest).where(
            HumanReviewRequest.issuer == issuer,
            HumanReviewRequest.owner_id == owner,
            HumanReviewRequest.request_key == command.request_key,
        )
    )
    if prior is not None:
        if prior.request_digest != digest or prior.session_id != session_id:
            raise WorkflowError(409, "Human review request key was used for another request.")
        return {"request": await _view(db, prior)}
    # Database time is evaluated after waiting for locks, unlike transaction now().
    now = await db.scalar(select(func.clock_timestamp()))
    assert isinstance(now, datetime)
    scoped = (HumanReviewRequest.issuer == issuer, HumanReviewRequest.owner_id == owner)
    recent_case = await db.scalar(
        select(func.count())
        .select_from(HumanReviewRequest)
        .where(
            *scoped,
            HumanReviewRequest.session_id == session_id,
            HumanReviewRequest.requested_at >= now - timedelta(minutes=10),
        )
    )
    recent_owner = await db.scalar(
        select(func.count())
        .select_from(HumanReviewRequest)
        .where(
            *scoped,
            HumanReviewRequest.requested_at >= now - timedelta(hours=1),
        )
    )
    if (recent_case or 0) >= CASE_REQUEST_LIMIT or (recent_owner or 0) >= OWNER_REQUEST_LIMIT:
        raise WorkflowError(429, "Human review request limit reached. Please try again later.")
    assignment = await db.scalar(
        select(Escalation)
        .where(
            Escalation.session_id == session_id,
            Escalation.status.in_(["pending", "assigned", "in_review"]),
        )
        .order_by(
            case(
                (Escalation.status == "in_review", 0), (Escalation.status == "assigned", 1), else_=2
            ),
            Escalation.created_at,
            Escalation.id,
        )
        .limit(1)
        .with_for_update()
    )
    if assignment is None:
        assignment = Escalation(
            id=uuid.uuid4(),
            session_id=session_id,
            status="pending",
            reason="Customer requested human review through the Assurely guide.",
        )
        db.add(assignment)
        await db.flush()
    row = HumanReviewRequest(
        id=uuid.uuid4(),
        issuer=issuer,
        owner_id=owner,
        session_id=session_id,
        request_key=command.request_key,
        request_digest=digest,
        escalation_id=assignment.id,
    )
    db.add(row)
    await db.flush()
    return {"request": await _view(db, row)}
