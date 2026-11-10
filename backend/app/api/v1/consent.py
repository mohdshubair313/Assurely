"""Durable consent receipts and deletion for returning-user profile memory."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult

from app.core.config import get_settings
from app.core.consent import purpose_version
from app.core.security import require_authenticated_user_id, require_matching_user_id
from app.db.session import AsyncSessionLocal
from app.models.db.auth_identity import AuthEvent
from app.models.db.consent_record import ConsentRecord
from app.models.db.user import User
from app.models.db.user_profile_memory import UserProfileMemory

router = APIRouter()


class ConsentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: uuid.UUID
    scope: Literal[
        "process_comparison",
        "save_profile",
        "receive_updates",
        "voice_demo",
        "voice_microphone",
        "voice_vendor_processing",
        "voice_transcription",
        "voice_summary",
        "voice_report_speech",
    ]
    action: Literal["grant", "revoke"]
    purpose_version: str | None = Field(default=None, max_length=40)


class ConsentResponse(BaseModel):
    user_id: str
    scope: str
    status: str
    timestamp: str
    purpose_version: str


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
    clerk = get_settings().auth_provider == "clerk"
    voice_scope = req.scope.startswith("voice_")
    current_version = purpose_version(req.scope)
    version = current_version if clerk or voice_scope else (req.purpose_version or "legacy-v0")
    if (clerk or voice_scope) and req.action == "grant" and req.purpose_version != current_version:
        raise HTTPException(422, "Read and accept the current consent purpose before granting.")
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as db:
        await db.execute(
            insert(User)
            .values(id=req.user_id, role="customer")
            .on_conflict_do_nothing(index_elements=[User.id])
        )
        # Same order as voice start/end/recovery: entitlement before consent/session mutations.
        # No microphone/vendor consent is inferred from this separate synthetic-demo purpose.
        voice_entitlement = None
        if voice_scope:
            from app.voice.service import VoiceSessionService

            voice_entitlement = await VoiceSessionService.lock_entitlement(db, req.user_id)
        if req.action == "grant":
            # Keep previous receipts; replace an old active version rather than relabel it.
            if clerk:
                await db.execute(
                    update(ConsentRecord)
                    .where(
                        ConsentRecord.user_id == req.user_id,
                        ConsentRecord.scope == req.scope,
                        ConsentRecord.revoked_at.is_(None),
                        ConsentRecord.purpose_version != version,
                    )
                    .values(revoked_at=now)
                )
            await db.execute(
                insert(ConsentRecord)
                .values(user_id=req.user_id, scope=req.scope, purpose_version=version)
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
            if req.scope == "voice_demo" and voice_entitlement is not None:
                service = VoiceSessionService(AsyncSessionLocal, get_settings())
                await service.check_balance(db, voice_entitlement)
                await service.expire_locked(
                    db, voice_entitlement, await service.now(db), revoked=True
                )
                await service.check_balance(db, voice_entitlement)
            if (
                req.scope in ("voice_microphone", "voice_vendor_processing")
                and voice_entitlement is not None
            ):
                from app.models.db.voice import VoiceSession
                from app.models.db.voice_lifecycle import VoiceManagedOperation

                # Existing entitlement lock serializes this revocation with connection issuance.
                # Do not release usage or infer media termination from consent withdrawal.
                sessions = (
                    await db.scalars(
                        select(VoiceSession)
                        .where(
                            VoiceSession.user_id == req.user_id,
                            VoiceSession.source_mode == "synthetic-vaani",
                            VoiceSession.state.in_(("reserved", "active")),
                        )
                        .order_by(VoiceSession.id)
                        .with_for_update()
                    )
                ).all()
                for session in sessions:
                    operation = await db.get(
                        VoiceManagedOperation, session.id, with_for_update=True
                    )
                    if operation:
                        operation.end_requested = True
        if clerk:
            db.add(
                AuthEvent(
                    id=uuid.uuid4(),
                    user_id=req.user_id,
                    action=f"consent_{req.action}",
                    details={
                        "scope": req.scope,
                        "purpose_version": version,
                        "issuer": get_settings().auth_issuer,
                    },
                )
            )
            if req.action == "grant":
                granted_at = await db.scalar(
                    select(ConsentRecord.granted_at).where(
                        ConsentRecord.user_id == req.user_id,
                        ConsentRecord.scope == req.scope,
                        ConsentRecord.revoked_at.is_(None),
                    )
                )
                if granted_at is not None:
                    now = granted_at
        await db.commit()

    return ConsentResponse(
        user_id=str(req.user_id),
        scope=req.scope,
        status="granted" if req.action == "grant" else "revoked",
        timestamp=now.isoformat(),
        purpose_version=version,
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
            await db.execute(delete(UserProfileMemory).where(UserProfileMemory.user_id == user_id)),
        )
        await db.commit()
    return ProfileMemoryDeletionResponse(user_id=str(user_id), deleted=bool(result.rowcount))
