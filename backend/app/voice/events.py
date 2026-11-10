"""Authenticated, minimized durable Vaani receipts and bounded synthetic reconciliation."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import uuid
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal, InvalidOperation

from fastapi import HTTPException
from pydantic import AwareDatetime, BaseModel, Field, ValidationError
from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models.db.voice import VoiceEntitlement, VoiceSession
from app.models.db.voice_provider import VoiceProviderCall, VoiceProviderEvent
from app.voice.service import OPEN_STATES, VoiceSessionService
from app.voice.vaani import valid_room

MAX_BODY = 262144


class EventFields(BaseModel):
    event: str = Field(pattern=r"^[a-z_]{1,80}$")
    timestamp: AwareDatetime
    data: dict[str, object]
    call_id: str | None = None


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate field")
        result[key] = value
    return result


def normalize(raw: bytes, signature: str, secret: str) -> VoiceProviderEvent:
    if len(secret) < 32:
        raise HTTPException(503, "Provider webhook signing is not configured.")
    if not raw or len(raw) > MAX_BODY:
        raise HTTPException(413, "Provider event exceeds the permitted size.")
    if not re.fullmatch(r"(?:sha256=)?[a-fA-F0-9]{64}", signature):
        raise HTTPException(401, "Provider event signature is invalid.")
    supplied = signature.removeprefix("sha256=").lower()
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(401, "Provider event signature is invalid.")
    try:
        body = json.loads(raw, object_pairs_hook=_pairs)
        event = EventFields.model_validate(body)
        if not isinstance(body.get("timestamp"), str):
            raise ValueError("Timestamp")
        if signature.startswith("sha256=") != (event.event == "call_postprocessing"):
            raise ValueError("Signature family")
        rooms = [
            x
            for x in (event.data.get("room_name"), event.data.get("call_id"), event.call_id)
            if x is not None
        ]
        if (
            not rooms
            or not all(isinstance(x, str) and valid_room(x) for x in rooms)
            or len(set(rooms)) != 1
        ):
            raise ValueError("Call binding")
        raw_duration = event.data.get("call_duration")
        duration = None
        if raw_duration is not None:
            if isinstance(raw_duration, bool):
                raise ValueError("Duration")
            duration = Decimal(str(raw_duration))
            if not duration.is_finite() or not 0 <= duration <= 86400:
                raise ValueError("Duration")
            duration = duration.quantize(Decimal("0.001"), rounding=ROUND_CEILING)
        return VoiceProviderEvent(
            id=uuid.uuid4(),
            digest=hashlib.sha256(raw).hexdigest(),
            event=event.event,
            room=str(rooms[0]),
            event_at=event.timestamp,
            duration=duration,
            status="received",
        )
    except (
        ValueError,
        TypeError,
        ValidationError,
        InvalidOperation,
        AttributeError,
        RecursionError,
    ):
        raise HTTPException(422, "Provider event contract is invalid.") from None


async def receive_event(
    factory: async_sessionmaker[AsyncSession], settings: Settings, raw: bytes, signature: str
) -> bool:
    if not settings.vaani_ingress_enabled:
        raise HTTPException(503, "Provider event ingress is disabled.")
    event = normalize(raw, signature, settings.vaani_webhook_secret.get_secret_value())
    age = (datetime.now(UTC) - event.event_at).total_seconds()
    if age > 300 or age < -30:
        event.status, event.reason = "quarantined", "timestamp_window"
    async with factory() as db:
        result = await db.scalar(
            insert(VoiceProviderEvent)
            .values(
                id=event.id,
                digest=event.digest,
                event=event.event,
                room=event.room,
                event_at=event.event_at,
                duration=event.duration,
                status=event.status,
                reason=event.reason,
            )
            .on_conflict_do_nothing(index_elements=[VoiceProviderEvent.digest])
            .returning(VoiceProviderEvent.id)
        )
        await db.commit()  # Acknowledge only durable receipts; no transcript/body is stored.
        return result is None


async def process_events(factory: async_sessionmaker[AsyncSession], settings: Settings) -> int:
    """Idempotent worker; lock entitlement -> session -> binding -> event in every path."""
    service = VoiceSessionService(factory, settings)
    async with factory() as db:
        hints = (
            await db.execute(
                select(VoiceProviderEvent.id, VoiceProviderEvent.room)
                .where(
                    or_(
                        VoiceProviderEvent.status == "received",
                        and_(
                            VoiceProviderEvent.status == "unmatched",
                            VoiceProviderEvent.room.in_(select(VoiceProviderCall.room)),
                        ),
                    )
                )
                .order_by(VoiceProviderEvent.created_at, VoiceProviderEvent.id)
                .limit(100)
            )
        ).all()
    processed = 0
    for event_id, room in hints:
        async with factory() as db:
            owner = await db.scalar(
                select(VoiceSession.user_id)
                .join(VoiceProviderCall, VoiceProviderCall.session_id == VoiceSession.id)
                .where(VoiceProviderCall.room == room)
            )
            if owner is None:
                event = await db.get(VoiceProviderEvent, event_id, with_for_update=True)
                if event and event.status == "received":
                    event.status, event.reason = "unmatched", "unknown_call"
                    await db.commit()
                continue
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
            event = await db.get(VoiceProviderEvent, event_id, with_for_update=True)
            if not event or event.status not in ("received", "unmatched"):
                continue
            if not ent or not session or not call:
                event.status, event.reason = "quarantined", "missing_binding"
            elif (
                not call.synthetic
                or session.provider != "vaani"
                or session.source_mode != "synthetic-vaani"
                or session.case_session_id is not None
                or ent.provider != "test"
            ):
                event.status, event.reason = "quarantined", "non_synthetic_call"
            else:
                await service.check_balance(db, ent)
                await _reconcile(db, service, ent, session, call, event)
                await service.check_balance(db, ent)
            await db.commit()
            processed += 1
    return processed


async def _reconcile(
    db: AsyncSession,
    service: VoiceSessionService,
    ent: VoiceEntitlement,
    session: VoiceSession,
    call: VoiceProviderCall,
    event: VoiceProviderEvent,
) -> None:
    event.status = "processed"
    if event.event_at.timestamp() < session.created_at.timestamp() - 30:
        event.status, event.reason = "quarantined", "before_session"
        return
    if event.event == "call_started":
        if session.state in OPEN_STATES and call.phase in ("ready", "active"):
            call.phase, session.state = "active", "active"
            call.last_event_at = max(call.last_event_at or event.event_at, event.event_at)
    elif event.event == "call_ended":
        if event.duration is None or event.duration > session.reserved_seconds:
            call.phase = "reconciling"
            event.status, event.reason = "quarantined", "duration_uncertain"
            return
        if call.last_event_at and event.event_at < call.last_event_at:
            event.status, event.reason = "quarantined", "contradictory_timestamp"
            return
        if session.state not in OPEN_STATES:
            if call.measured_seconds != event.duration:
                call.phase = "reconciling"
                event.status, event.reason = "quarantined", "terminal_conflict"
            return
        used = int(event.duration.to_integral_value(rounding=ROUND_CEILING))
        ent.reserved_seconds -= session.reserved_seconds
        ent.consumed_seconds += used
        ent.updated_at = await service.now(db)
        session.state, session.consumed_seconds = "ended", used
        session.ended_at = event.event_at
        call.phase, call.measured_seconds, call.last_event_at = (
            "ended",
            event.duration,
            event.event_at,
        )
        service._entry(db, ent, session, "settlement", used)
        service._entry(db, ent, session, "release", session.reserved_seconds - used)
    elif event.event == "call_postprocessing":
        # Optional vendor analysis is never the primary duration/approval source.
        if call.measured_seconds is not None and event.duration != call.measured_seconds:
            call.phase = "reconciling"
            event.status, event.reason = "quarantined", "analysis_duration_conflict"
    elif event.event in ("call_failed", "call_no_answer", "call_rejected", "call_user_busy"):
        if session.state in OPEN_STATES:
            call.phase = "reconciling"  # No inference of zero cost from a failure label.
    elif not event.event.startswith("human_transfer_"):
        event.reason = "informational_or_unknown"
