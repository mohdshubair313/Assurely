"""Cross-worker execution locks and owner-authorized orphan-turn invalidation."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.correlation import database_session_id
from app.db import report_release
from app.db.policy_review_store import WorkflowError
from app.db.session import AsyncSessionLocal
from app.db.source_review import ClosedModel
from app.models.db.report_release import TurnRecoveryReceipt


class RecoveryCommand(ClosedModel):
    turn_id: UUID
    request_key: UUID


@asynccontextmanager
async def execution_guard(issuer: str, session_id: str) -> AsyncIterator[AsyncSession | None]:
    if get_settings().environment == "development":
        yield None
        return
    if not issuer.strip():
        raise WorkflowError(503, "Turn identity issuer is not configured.")
    # Dedicated transaction/connection stays open through the graph call. A
    # process crash closes it. No timer may abort a worker still holding this lock.
    async with AsyncSessionLocal() as db, db.begin():
        acquired = await db.scalar(text(
            "SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))"
        ), {"key": f"graph-run:{issuer}:{database_session_id(session_id)}"})
        if not acquired:
            raise WorkflowError(409, "This session is being processed; retry later.")
        yield db


async def recover(
    db: AsyncSession, issuer: str, session_id: str, owner: UUID, command: RecoveryCommand,
) -> dict[str, Any]:
    """Caller must hold execution_guard; recovery never resumes external effects."""
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                     {"key": f"turn-recovery:{issuer}:{owner}:{command.request_key}"})
    row = await report_release.head(db, issuer, session_id, owner)
    receipt = await db.scalar(select(TurnRecoveryReceipt).where(
        TurnRecoveryReceipt.issuer == issuer, TurnRecoveryReceipt.owner_id == owner,
        TurnRecoveryReceipt.request_key == command.request_key,
    ))
    if receipt is not None:
        if receipt.session_id != row.session_id or receipt.turn_id != command.turn_id:
            raise WorkflowError(409, "Recovery request key is already bound.")
        return {"receipt_id": str(receipt.id), "turn_id": str(receipt.turn_id),
                "action": "interrupted_turn_closed", "delivery_hold": True,
                "historical_receipt": True}
    if row.turn_id != command.turn_id or row.status != "running":
        raise WorkflowError(409, "The interrupted turn changed or is already closed.")
    row.status, row.report_digest, row.guardrail_approved = "failed", None, False
    receipt = TurnRecoveryReceipt(id=uuid4(), issuer=issuer, session_id=row.session_id,
                                  owner_id=owner, turn_id=command.turn_id,
                                  request_key=command.request_key)
    db.add(receipt)
    await db.flush()
    return {"receipt_id": str(receipt.id), "turn_id": str(receipt.turn_id),
            "action": "interrupted_turn_closed", "delivery_hold": True,
            "historical_receipt": True}
