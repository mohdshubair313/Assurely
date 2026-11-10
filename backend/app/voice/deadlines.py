"""Durable synthetic Vaani deadline detection, without inferring provider termination.

This worker only requests future termination work. A deadline or lost browser/BYOL
connection is not proof that provider media ended, so reservations remain untouched.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models.db.voice import VoiceEntitlement, VoiceSession
from app.models.db.voice_provider import VoiceProviderCall
from app.voice.service import OPEN_STATES, VoiceSessionService

PENDING_PHASES = ("ready", "active", "reconciling")


async def mark_expired_provider_calls(
    factory: async_sessionmaker[AsyncSession], settings: Settings
) -> int:
    """Mark persisted, expired synthetic bindings for termination; never settle usage.

    Discovery is only a hint. Each mutation rechecks eligibility under entitlement
    -> session -> binding locks, matching ingress/BYOL ordering. The marker survives
    restarts and repeated workers do not enqueue duplicate work. Disabled dispatch
    flags do not suppress recovery of already-persisted provider sessions.
    """
    service = VoiceSessionService(factory, settings)
    async with factory() as db:
        now = await service.now(db)
        hints = (
            await db.execute(
                select(VoiceSession.id, VoiceSession.user_id)
                .join(VoiceProviderCall, VoiceProviderCall.session_id == VoiceSession.id)
                .join(VoiceEntitlement, VoiceEntitlement.user_id == VoiceSession.user_id)
                .where(
                    VoiceSession.provider == "vaani",
                    VoiceSession.source_mode == "synthetic-vaani",
                    VoiceSession.case_session_id.is_(None),
                    VoiceSession.state.in_(OPEN_STATES),
                    VoiceSession.expires_at <= now,
                    VoiceProviderCall.synthetic.is_(True),
                    VoiceProviderCall.phase.in_(PENDING_PHASES),
                    VoiceEntitlement.provider == "test",
                )
                .order_by(VoiceEntitlement.id, VoiceSession.id)
                .limit(100)
            )
        ).all()

    marked = 0
    for session_id, owner in hints:
        async with factory() as db:
            ent = await service.lock_entitlement(db, owner)
            session = await db.scalar(
                select(VoiceSession).where(VoiceSession.id == session_id).with_for_update()
            )
            call = await db.scalar(
                select(VoiceProviderCall)
                .where(VoiceProviderCall.session_id == session_id)
                .with_for_update()
            )
            if (
                ent is None
                or ent.provider != "test"
                or session is None
                or session.user_id != ent.user_id
                or session.provider != "vaani"
                or session.source_mode != "synthetic-vaani"
                or session.case_session_id is not None
                or session.state not in OPEN_STATES
                or call is None
                or not call.synthetic
                or call.phase not in PENDING_PHASES
                or session.expires_at > await service.now(db)
            ):
                continue
            await service.check_balance(db, ent)
            call.phase = "termination_required"
            await service.check_balance(db, ent)
            await db.commit()
            marked += 1
    return marked
