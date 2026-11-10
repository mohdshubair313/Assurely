"""Authenticated synthetic-only BYOL preparation. No LLM, RAG, case output or free advice."""

from __future__ import annotations

import uuid
from datetime import timedelta

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.consent import VOICE_CONSENT_VERSION
from app.models.db.auth_identity import AuthIdentity
from app.models.db.consent_record import ConsentRecord
from app.models.db.voice import VoiceSession
from app.models.db.voice_provider import VoiceProviderCall, VoiceProviderEvent
from app.voice.service import OPEN_STATES, VoiceSessionService
from app.voice.vaani import valid_room

SAFE_RESPONSE = (
    "I am an AI insurance guide. This development session cannot verify insurance information. "
    "Please use Assurely's evidence-based text journey for policy questions."
)


class SpeechMessage(BaseModel):
    role: str = Field(max_length=20)
    content: str = Field(max_length=4000)


class ByolTurn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    interaction_type: str
    response_id: int = Field(strict=True, ge=1, le=2147483647)
    call_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,160}$")
    transcript: list[SpeechMessage] = Field(max_length=100)
    req_body: dict[str, object] | None = None


class BindingDeniedError(Exception):
    pass


async def eligible(
    db: AsyncSession,
    session: VoiceSession,
    call: VoiceProviderCall,
    settings: Settings,
    service: VoiceSessionService,
) -> bool:
    try:
        configured = uuid.UUID(settings.vaani_agent_id)
    except ValueError:
        return False
    identity = await db.scalar(
        select(AuthIdentity).where(
            AuthIdentity.user_id == session.user_id,
            AuthIdentity.provider == "clerk",
            AuthIdentity.disabled.is_(False),
            AuthIdentity.issuer == settings.auth_issuer,
        )
    )
    scopes = set(
        (
            await db.scalars(
                select(ConsentRecord.scope).where(
                    ConsentRecord.user_id == session.user_id,
                    ConsentRecord.revoked_at.is_(None),
                    ConsentRecord.purpose_version == VOICE_CONSENT_VERSION,
                )
            )
        ).all()
    )
    return bool(
        identity
        and call.agent_id == configured
        and call.synthetic
        and session.provider == "vaani"
        and session.source_mode == "synthetic-vaani"
        and session.case_session_id is None
        and session.state in OPEN_STATES
        and service.test_access(session.user_id)
        and {"voice_microphone", "voice_vendor_processing"} <= scopes
        and session.expires_at > await service.now(db)
    )


async def bind_synthetic_call(
    factory: async_sessionmaker[AsyncSession], settings: Settings, session_id: uuid.UUID, room: str
) -> None:
    """Internal V2b seam, not a public binding endpoint. No ownership comes from a webhook."""
    if not valid_room(room):
        raise BindingDeniedError()
    async with factory() as db:
        owner = await db.scalar(select(VoiceSession.user_id).where(VoiceSession.id == session_id))
        if owner is None:
            raise BindingDeniedError()
        service = VoiceSessionService(factory, settings)
        ent = await service.lock_entitlement(db, owner)
        session = await db.scalar(
            select(VoiceSession).where(VoiceSession.id == session_id).with_for_update()
        )
        if not ent or not session or ent.provider != "test" or ent.status != "active":
            raise BindingDeniedError()
        try:
            agent_id = uuid.UUID(settings.vaani_agent_id)
        except ValueError:
            raise BindingDeniedError() from None
        call = VoiceProviderCall(
            session_id=session_id,
            room=room,
            agent_id=agent_id,
            synthetic=True,
            phase="ready",
            last_response_id=0,
        )
        if not await eligible(db, session, call, settings, service):
            raise BindingDeniedError()
        await service.check_balance(db, ent)
        existing = await db.get(VoiceProviderCall, session_id)
        if existing:
            if existing.room != room or existing.agent_id != agent_id:
                raise BindingDeniedError()
        else:
            db.add(call)
        await db.execute(
            update(VoiceProviderEvent)
            .where(VoiceProviderEvent.room == room, VoiceProviderEvent.status == "unmatched")
            .values(status="received", reason=None)
        )
        await db.commit()


async def authorize_connection(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    room: str,
    connection_id: uuid.UUID,
    response_id: int | None = None,
) -> None:
    service = VoiceSessionService(factory, settings)
    async with factory() as db:
        owner = await db.scalar(
            select(VoiceSession.user_id)
            .join(VoiceProviderCall, VoiceProviderCall.session_id == VoiceSession.id)
            .where(VoiceProviderCall.room == room)
        )
        if owner is None:
            raise BindingDeniedError()
        ent = await service.lock_entitlement(db, owner)
        session = await db.scalar(
            select(VoiceSession)
            .join(VoiceProviderCall, VoiceProviderCall.session_id == VoiceSession.id)
            .where(VoiceProviderCall.room == room)
            .with_for_update(of=VoiceSession)
        )
        call = await db.scalar(
            select(VoiceProviderCall).where(VoiceProviderCall.room == room).with_for_update()
        )
        if (
            not ent
            or ent.provider != "test"
            or ent.status != "active"
            or not session
            or not call
            or call.phase not in ("ready", "active")
            or not await eligible(db, session, call, settings, service)
        ):
            raise BindingDeniedError()
        if settings.voice_byol_evidence_enabled:
            from app.models.db.voice_lifecycle import VoiceManagedOperation

            operation = await db.get(VoiceManagedOperation, session.id, with_for_update=True)
            if operation is None or operation.end_requested or operation.phase != "connected":
                raise BindingDeniedError()
        now = await service.now(db)
        if (
            call.byol_connection_id
            and call.byol_connection_id != connection_id
            and call.byol_lease_until
            and call.byol_lease_until > now
        ):
            raise BindingDeniedError()
        if response_id is not None:
            if response_id <= call.last_response_id:
                raise BindingDeniedError()
            call.last_response_id = response_id
        call.byol_connection_id = connection_id
        call.byol_lease_until = now + timedelta(seconds=20)
        await db.commit()


async def release_connection(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    room: str,
    connection_id: uuid.UUID,
) -> None:
    async with factory() as db:
        owner = await db.scalar(
            select(VoiceSession.user_id)
            .join(VoiceProviderCall, VoiceProviderCall.session_id == VoiceSession.id)
            .where(VoiceProviderCall.room == room)
        )
        if owner is None:
            return
        await VoiceSessionService.lock_entitlement(db, owner)
        call = await db.scalar(
            select(VoiceProviderCall).where(VoiceProviderCall.room == room).with_for_update()
        )
        if call and call.byol_connection_id == connection_id:
            call.byol_connection_id, call.byol_lease_until = None, None
        await db.commit()
