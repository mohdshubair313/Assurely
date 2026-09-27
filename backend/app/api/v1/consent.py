"""Durable consent receipts and deletion for returning-user profile memory."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult

from app.core.security import require_authenticated_user_id, require_matching_user_id
from app.db.session import AsyncSessionLocal
from app.models.db.consent_record import ConsentRecord
from app.models.db.user import User
from app.models.db.user_profile_memory import UserProfileMemory

router = APIRouter()


class ConsentRequest(BaseModel):
    user_id: uuid.UUID
    scope: Literal["process_comparison", "save_profile", "receive_updates"]
    action: Literal["grant", "revoke"]


class ConsentResponse(BaseModel):
    user_id: str
    scope: str
    status: str
    timestamp: str


class ProfileMemoryDeletionResponse(BaseModel):
    user_id: str
    deleted: bool


@router.post("/consent", response_model=ConsentResponse)
async def update_consent(
    req: ConsentRequest,
    authenticated_user_id: Annotated[uuid.UUID, Depends(require_authenticated_user_id)],
) -> ConsentResponse:
    """Persist consent and immediately erase profile memory when consent is revoked."""
    require_matching_user_id(authenticated_user_id, req.user_id)
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as db:
        await db.execute(
            insert(User)
            .values(id=req.user_id, role="customer")
            .on_conflict_do_nothing(index_elements=[User.id])
        )
        if req.action == "grant":
            await db.execute(
                insert(ConsentRecord)
                .values(user_id=req.user_id, scope=req.scope)
                .on_conflict_do_nothing(
                    index_elements=[ConsentRecord.user_id, ConsentRecord.scope],
                    index_where=ConsentRecord.revoked_at.is_(None),
                )
            )
        else:
            await db.execute(
                update(ConsentRecord)
                .where(
                    ConsentRecord.user_id == req.user_id,
                    ConsentRecord.scope == req.scope,
                    ConsentRecord.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            if req.scope == "save_profile":
                await db.execute(
                    delete(UserProfileMemory).where(UserProfileMemory.user_id == req.user_id)
                )
        await db.commit()

    return ConsentResponse(
        user_id=str(req.user_id),
        scope=req.scope,
        status="granted" if req.action == "grant" else "revoked",
        timestamp=now.isoformat(),
    )


@router.delete("/profile-memory/{user_id}", response_model=ProfileMemoryDeletionResponse)
async def delete_profile_memory(
    user_id: uuid.UUID,
    authenticated_user_id: Annotated[uuid.UUID, Depends(require_authenticated_user_id)],
) -> ProfileMemoryDeletionResponse:
    """Delete the stored family profile snapshot for a user identity."""
    require_matching_user_id(authenticated_user_id, user_id)
    async with AsyncSessionLocal() as db:
        result = cast(
            CursorResult[Any],
            await db.execute(
                delete(UserProfileMemory).where(UserProfileMemory.user_id == user_id)
            ),
        )
        await db.commit()
    return ProfileMemoryDeletionResponse(user_id=str(user_id), deleted=bool(result.rowcount))
