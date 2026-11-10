"""Independent, restart-safe MOCK expiry worker.

Run once: python -m app.voice.recovery --once
Run continuously: python -m app.voice.recovery
No real provider calls, expiry inference, or paid-period resets are performed.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Callable

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models.db.voice import VoiceEntitlement, VoiceSession
from app.voice.service import VoiceSessionService

logger = logging.getLogger(__name__)


async def recover_once(factory: async_sessionmaker[AsyncSession], settings: Settings) -> int:
    service = VoiceSessionService(factory, settings)
    # Discovery is an unlocked hint. Recheck only after the entitlement lock.
    async with factory() as db:
        now = await service.now(db)
        due = select(VoiceSession.user_id).where(
            VoiceSession.provider == "mock",
            or_(
                and_(VoiceSession.state == "active", VoiceSession.expires_at <= now),
                and_(VoiceSession.state == "reserved", VoiceSession.recovery_after <= now),
            ),
        )
        owners = (
            await db.scalars(
                select(VoiceEntitlement.user_id)
                .where(VoiceEntitlement.user_id.in_(due))
                .order_by(VoiceEntitlement.id)
                .limit(100)
            )
        ).all()
    count = 0
    failed = False
    for user_id in owners:
        try:
            async with factory() as db:
                ent = await db.scalar(
                    select(VoiceEntitlement)
                    .where(VoiceEntitlement.user_id == user_id)
                    .with_for_update(skip_locked=True)
                )
                if ent is None:
                    continue  # Another request/worker owns this entitlement; retry next pass.
                await service.check_balance(db, ent)
                count += await service.expire_locked(db, ent, await service.now(db))
                await service.check_balance(db, ent)
                await db.commit()
        except Exception:
            failed = True
            logger.error("Synthetic voice recovery transaction failed; retry required")
    if failed:
        raise RuntimeError("Synthetic voice recovery requires retry or operator reconciliation")
    return count


async def recovery_loop(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    health: Callable[[bool], None] | None = None,
) -> None:
    while True:
        try:
            await recover_once(factory, settings)
            from app.voice.events import process_events

            await process_events(factory, settings)
            from app.voice.deadlines import mark_expired_provider_calls

            await mark_expired_provider_calls(factory, settings)
            from app.voice.managed import recover_managed

            await recover_managed(factory, settings)
            if health:
                health(True)
        except Exception:
            if health:
                health(False)
            # Durable deadlines/ledger remain intact. Do not log payloads or exception values.
            logger.error("Synthetic voice recovery pass failed; durable work remains pending")
        await asyncio.sleep(settings.voice_recovery_interval_seconds)


def main() -> None:
    from app.core.config import get_settings
    from app.db.session import AsyncSessionLocal

    parser = argparse.ArgumentParser(description="Recover synthetic voice lifecycle deadlines")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    if args.once:

        async def run_once() -> tuple[int, int, int, int]:
            from app.voice.deadlines import mark_expired_provider_calls
            from app.voice.events import process_events
            from app.voice.managed import recover_managed

            return (
                await recover_once(AsyncSessionLocal, settings),
                await process_events(AsyncSessionLocal, settings),
                await mark_expired_provider_calls(AsyncSessionLocal, settings),
                await recover_managed(AsyncSessionLocal, settings),
            )

        recovered, processed, marked, managed = asyncio.run(run_once())
        print(
            f"Recovered synthetic sessions: {recovered}; processed provider events: {processed}; "
            f"provider deadlines marked: {marked}; managed operations checked: {managed}"
        )
    else:
        asyncio.run(recovery_loop(AsyncSessionLocal, settings))


if __name__ == "__main__":
    main()
