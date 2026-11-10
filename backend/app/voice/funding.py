"""Funding-period allocation over the existing session/usage ledger, test mode only.

No reset, duplicate ledger, payment API or external call. The aggregate entitlement
remains a lifetime reconciliation counter; the locked period independently bounds spend.
"""

import uuid
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.db.voice import VoiceEntitlement, VoiceSession
from app.models.db.voice_lifecycle import (
    VoiceFundingAllocation,
    VoiceFundingPeriod,
    VoiceSubscription,
)
from app.voice.billing import test_gate
from app.voice.service import OPEN_STATES


async def allocate_period(
    db: AsyncSession, ent: VoiceEntitlement, settings: Settings, now: datetime, cap: int
) -> uuid.UUID | None:
    """Caller holds entitlement. Lock period before session/operation mutations."""
    if not settings.voice_funded_test_enabled:
        return None
    test_gate(settings)
    periods = (
        await db.scalars(
            select(VoiceFundingPeriod)
            .join(
                VoiceSubscription,
                VoiceSubscription.external_id == VoiceFundingPeriod.subscription_id,
            )
            .where(
                VoiceFundingPeriod.user_id == ent.user_id,
                VoiceSubscription.user_id == ent.user_id,
                VoiceSubscription.status == "active",
                VoiceFundingPeriod.period_start <= now,
                VoiceFundingPeriod.period_end > now,
                VoiceFundingPeriod.status.in_(("funded_test", "available_test")),
            )
            .order_by(VoiceFundingPeriod.period_start)
            .with_for_update(of=VoiceFundingPeriod)
        )
    ).all()
    if len(periods) != 1:
        raise HTTPException(402, "No unambiguous funded test period is available.")
    period = periods[0]
    used = int(
        await db.scalar(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (VoiceSession.state.in_(OPEN_STATES), VoiceSession.reserved_seconds),
                            else_=VoiceSession.consumed_seconds,
                        )
                    ),
                    0,
                )
            )
            .join(VoiceFundingAllocation, VoiceFundingAllocation.session_id == VoiceSession.id)
            .where(VoiceFundingAllocation.period_id == period.id)
        )
        or 0
    )
    if used < 0 or period.included_seconds - used < cap:
        raise HTTPException(402, "The current test period has insufficient available seconds.")
    if period.status == "funded_test":
        ent.included_seconds += period.included_seconds
        period.status = "available_test"
    return period.id
