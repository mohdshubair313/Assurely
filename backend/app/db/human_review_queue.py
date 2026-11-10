"""Bounded operator intake; a queue entry is never notification or approval."""

from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.policy_review_store import WorkflowError
from app.models.db.escalation import Escalation
from app.models.db.human_review import HumanReviewRequest
from app.models.db.session import Session


def queue_query(issuer: str, limit: int) -> Any:
    """Select one latest request per active escalation, with no customer content."""
    if not issuer.strip():
        raise WorkflowError(503, "Human review identity issuer is not configured.")
    if isinstance(limit, bool) or not 1 <= limit <= 100:
        raise WorkflowError(422, "Queue limit must be between 1 and 100.")
    latest = (
        select(
            HumanReviewRequest.id.label("request_id"),
            HumanReviewRequest.escalation_id,
            HumanReviewRequest.session_id,
            HumanReviewRequest.requested_at,
            Escalation.status,
            func.row_number()
            .over(
                partition_by=HumanReviewRequest.escalation_id,
                order_by=(HumanReviewRequest.requested_at.desc(), HumanReviewRequest.id.desc()),
            )
            .label("position"),
        )
        .join(Escalation, Escalation.id == HumanReviewRequest.escalation_id)
        .join(Session, Session.id == HumanReviewRequest.session_id)
        .where(
            HumanReviewRequest.issuer == issuer,
            Session.user_id == HumanReviewRequest.owner_id,
            Escalation.session_id == HumanReviewRequest.session_id,
            Escalation.status.in_(["pending", "assigned", "in_review"]),
        )
        .subquery()
    )
    return (
        select(
            latest.c.escalation_id,
            latest.c.session_id,
            latest.c.request_id,
            latest.c.requested_at,
            latest.c.status,
        )
        .where(latest.c.position == 1)
        .order_by(latest.c.requested_at, latest.c.request_id)
        .limit(limit + 1)
    )


async def read_queue(db: AsyncSession, issuer: str, limit: int = 25) -> dict[str, Any]:
    # Validate before even querying schema availability; never interpolate identity values.
    query = queue_query(issuer, limit)
    if not await db.scalar(text("SELECT to_regclass('human_review_requests')")):
        raise WorkflowError(503, "Human review queue storage is unavailable.")
    rows = (await db.execute(query)).mappings().all()
    return {
        "items": [dict(row) for row in rows[:limit]],
        "truncated": len(rows) > limit,
        "pagination": "first_page_only",
        "notification_confirmed": False,
        "delivery_authorized": False,
    }
