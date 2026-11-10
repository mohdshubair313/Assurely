"""Durable synthetic lifecycle. No Vaani dispatch or real-media termination.

Lock order for every mutation: entitlement -> sessions (UUID order) -> receipts/ledger.
There is no paid period reset in V1; the existing period is never overwritten.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.consent import VOICE_CONSENT_VERSION
from app.models.db.consent_record import ConsentRecord
from app.models.db.user import User
from app.models.db.voice import VoiceEntitlement, VoiceOperation, VoiceSession, VoiceUsageLedger
from app.voice.providers import MockVoiceProvider

OPEN_STATES = ("reserved", "active")


def request_digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


class VoiceSessionService:
    def __init__(self, factory: async_sessionmaker[AsyncSession], settings: Settings) -> None:
        self.factory = factory
        self.settings = settings

    def test_access(self, user_id: uuid.UUID) -> bool:
        try:
            return user_id in {uuid.UUID(value) for value in self.settings.voice_test_subjects}
        except (ValueError, TypeError) as exc:
            raise HTTPException(503, "Voice test access is not configured.") from exc

    def require_mock(self, user_id: uuid.UUID) -> None:
        if self.settings.voice_provider != "mock":
            raise HTTPException(
                503, "Live voice is not configured. The mock prototype is disabled."
            )
        if not self.test_access(user_id):
            raise HTTPException(403, "This no-audio prototype is limited to test accounts.")

    async def _ensure(self, db: AsyncSession, user_id: uuid.UUID, now: datetime) -> None:
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = (
            start.replace(year=start.year + 1, month=1)
            if start.month == 12
            else start.replace(month=start.month + 1)
        )
        await db.execute(insert(User).values(id=user_id, role="customer").on_conflict_do_nothing())
        await db.execute(
            insert(VoiceEntitlement)
            .values(
                user_id=user_id,
                provider="test",
                plan_code="local-mock",
                status="active",
                period_start=start,
                period_end=end,
                included_seconds=self.settings.voice_test_allowance_minutes * 60,
                concurrency_limit=self.settings.voice_max_concurrent_calls,
                max_call_seconds=self.settings.voice_max_call_seconds,
            )
            .on_conflict_do_nothing(index_elements=[VoiceEntitlement.user_id])
        )

    @staticmethod
    async def lock_entitlement(db: AsyncSession, user_id: uuid.UUID) -> VoiceEntitlement | None:
        return await db.scalar(
            select(VoiceEntitlement).where(VoiceEntitlement.user_id == user_id).with_for_update()
        )

    @staticmethod
    async def now(db: AsyncSession) -> datetime:
        value = await db.scalar(select(func.clock_timestamp()))
        assert isinstance(value, datetime)
        return value

    @staticmethod
    async def consented(db: AsyncSession, user_id: uuid.UUID) -> bool:
        return bool(
            await db.scalar(
                select(ConsentRecord.id).where(
                    ConsentRecord.user_id == user_id,
                    ConsentRecord.scope == "voice_demo",
                    ConsentRecord.purpose_version == VOICE_CONSENT_VERSION,
                    ConsentRecord.revoked_at.is_(None),
                )
            )
        )

    @staticmethod
    async def check_balance(db: AsyncSession, entitlement: VoiceEntitlement) -> None:
        await db.flush()
        rows = (
            await db.execute(
                select(VoiceUsageLedger.entry_type, func.sum(VoiceUsageLedger.seconds))
                .where(VoiceUsageLedger.entitlement_id == entitlement.id)
                .group_by(VoiceUsageLedger.entry_type)
            )
        ).all()
        values = {kind: int(amount) for kind, amount in rows}
        open_reservations = await db.scalar(
            select(func.coalesce(func.sum(VoiceSession.reserved_seconds), 0)).where(
                VoiceSession.user_id == entitlement.user_id, VoiceSession.state.in_(OPEN_STATES)
            )
        )
        reserved = (
            values.get("reservation", 0) - values.get("settlement", 0) - values.get("release", 0)
        )
        if (
            reserved != entitlement.reserved_seconds
            or open_reservations != entitlement.reserved_seconds
            or values.get("settlement", 0) != entitlement.consumed_seconds
            or min(entitlement.reserved_seconds, entitlement.consumed_seconds) < 0
            or entitlement.reserved_seconds + entitlement.consumed_seconds
            > entitlement.included_seconds
        ):
            raise HTTPException(503, "Voice usage requires operator reconciliation.")

    @staticmethod
    def _entry(
        db: AsyncSession, ent: VoiceEntitlement, session: VoiceSession, kind: str, seconds: int
    ) -> None:
        reference = f"{session.user_id}:{kind}:{session.id}"
        db.add(
            VoiceUsageLedger(
                entitlement_id=ent.id,
                session_id=session.id,
                entry_type=kind,
                seconds=seconds,
                settlement_reference=reference,
                idempotency_key=reference,
            )
        )

    async def terminal(
        self,
        db: AsyncSession,
        ent: VoiceEntitlement,
        session: VoiceSession,
        now: datetime,
        state: str,
        reason: str | None = None,
    ) -> None:
        if session.provider != "mock" or session.state not in OPEN_STATES:
            return
        used = (
            0
            if session.state == "reserved"
            else min(
                session.reserved_seconds,
                max(0, int((min(now, session.expires_at) - session.created_at).total_seconds())),
            )
        )
        # No max(0, balance) correction: a corrupt balance must fail and roll back.
        ent.reserved_seconds -= session.reserved_seconds
        ent.consumed_seconds += used
        ent.updated_at = now
        session.consumed_seconds = used
        session.state = state
        session.error_category = reason
        session.ended_at = min(now, session.expires_at)
        self._entry(db, ent, session, "settlement", used)
        self._entry(db, ent, session, "release", session.reserved_seconds - used)

    async def expire_locked(
        self, db: AsyncSession, ent: VoiceEntitlement, now: datetime, *, revoked: bool = False
    ) -> int:
        sessions = (
            await db.scalars(
                select(VoiceSession)
                .where(
                    VoiceSession.user_id == ent.user_id,
                    VoiceSession.provider == "mock",
                    VoiceSession.state.in_(OPEN_STATES),
                )
                .order_by(VoiceSession.id)
                .with_for_update()
            )
        ).all()
        count = 0
        for session in sessions:
            if (
                revoked
                or session.expires_at <= now
                or (session.state == "reserved" and session.recovery_after <= now)
            ):
                pending = session.state == "reserved"
                await self.terminal(
                    db,
                    ent,
                    session,
                    now,
                    "failed" if pending else "expired",
                    "consent_revoked"
                    if revoked
                    else ("mock_start_interrupted" if pending else "mock_deadline"),
                )
                count += 1
        return count

    async def _receipt(
        self, db: AsyncSession, user_id: uuid.UUID, operation: str, key: uuid.UUID, digest: str
    ) -> VoiceSession | None:
        receipt = await db.scalar(
            select(VoiceOperation).where(
                VoiceOperation.user_id == user_id,
                VoiceOperation.operation == operation,
                VoiceOperation.request_key == key,
            )
        )
        if receipt is None:
            return None
        if receipt.request_digest != digest:
            raise HTTPException(409, "The request key was already used with different inputs.")
        session = await db.scalar(
            select(VoiceSession).where(
                VoiceSession.id == receipt.session_id, VoiceSession.user_id == user_id
            )
        )
        if session is None:
            raise HTTPException(503, "Voice operation requires operator reconciliation.")
        return session

    async def start(
        self, user_id: uuid.UUID, language: str, key: uuid.UUID
    ) -> tuple[VoiceSession, bool]:
        self.require_mock(user_id)
        digest = request_digest({"language": language})
        async with self.factory() as db:
            await self._ensure(db, user_id, await self.now(db))
            ent = await self.lock_entitlement(db, user_id)
            assert ent is not None
            now = await self.now(db)
            await self.check_balance(db, ent)
            consent = await self.consented(db, user_id)
            await self.expire_locked(db, ent, now, revoked=not consent)
            await self.check_balance(db, ent)
            if not consent:
                await db.commit()
                raise HTTPException(403, "Accept the synthetic demo consent before starting.")
            existing = await self._receipt(db, user_id, "start", key, digest)
            if existing:
                await self.check_balance(db, ent)
                await db.commit()
                return existing, False
            if (
                ent.provider != "test"
                or ent.status != "active"
                or not (ent.period_start <= now < ent.period_end)
            ):
                raise HTTPException(402, "No active voice test allowance is available.")
            active = await db.scalar(
                select(func.count())
                .select_from(VoiceSession)
                .where(VoiceSession.user_id == user_id, VoiceSession.state.in_(OPEN_STATES))
            )
            if int(active or 0) >= ent.concurrency_limit:
                raise HTTPException(409, "The concurrent voice session limit has been reached.")
            reserve = min(
                ent.max_call_seconds,
                self.settings.voice_max_call_seconds,
                int((ent.period_end - now).total_seconds()),
            )
            if (
                reserve <= 0
                or ent.included_seconds - ent.reserved_seconds - ent.consumed_seconds < reserve
            ):
                raise HTTPException(402, "There are not enough voice minutes for the call limit.")
            session = VoiceSession(
                id=uuid.uuid4(),
                user_id=user_id,
                provider="mock",
                state="reserved",
                language=language,
                idempotency_key=key,
                request_digest=digest,
                reserved_seconds=reserve,
                consumed_seconds=0,
                created_at=now,
                expires_at=now + timedelta(seconds=reserve),
                recovery_after=now + timedelta(seconds=30),
                consent_snapshot={
                    "microphone": False,
                    "third_party_processing": False,
                    "transcription": False,
                    "summary_retention": False,
                    "demo_purpose_version": VOICE_CONSENT_VERSION,
                },
                source_mode="synthetic-fixture",
                trace_id=str(uuid.uuid4()),
            )
            db.add(session)
            await db.flush()
            db.add(
                VoiceOperation(
                    user_id=user_id,
                    operation="start",
                    request_key=key,
                    request_digest=digest,
                    session_id=session.id,
                )
            )
            self._entry(db, ent, session, "reservation", reserve)
            ent.reserved_seconds += reserve
            ent.updated_at = now
            await self.check_balance(db, ent)
            await db.commit()  # Durable intent exists before any provider work.
            session_id = session.id

        failed = False
        try:
            # This exact adapter has no network/media side effect. Never substitute a live one.
            await MockVoiceProvider().create_session(session_id=str(session_id), language=language)
        except Exception:
            failed = True
        async with self.factory() as db:
            ent = await self.lock_entitlement(db, user_id)
            assert ent is not None
            now = await self.now(db)
            await self.check_balance(db, ent)
            consent = await self.consented(db, user_id)
            await self.expire_locked(db, ent, now, revoked=not consent)
            recovered = await db.scalar(
                select(VoiceSession)
                .where(VoiceSession.id == session_id, VoiceSession.user_id == user_id)
                .with_for_update()
            )
            assert recovered is not None
            session = recovered
            if session.state == "reserved":
                if failed:
                    await self.terminal(db, ent, session, now, "failed", "mock_start_failed")
                else:
                    session.state = "active"
            await self.check_balance(db, ent)
            await db.commit()
            if failed:
                raise HTTPException(
                    503, "The synthetic demo could not start. Reservation released."
                )
            return session, True

    async def end(
        self, user_id: uuid.UUID, session_id: uuid.UUID, key: uuid.UUID | None = None
    ) -> VoiceSession:
        key = key or session_id  # Preserve existing empty-body end clients.
        digest = request_digest({"session_id": str(session_id)})
        async with self.factory() as db:
            ent = await self.lock_entitlement(db, user_id)
            session = await db.scalar(
                select(VoiceSession)
                .where(VoiceSession.id == session_id, VoiceSession.user_id == user_id)
                .with_for_update()
            )
            if session is None:
                raise HTTPException(404, "Voice session not found.")
            if ent is None or session.provider != "mock":
                raise HTTPException(503, "Live termination requires provider reconciliation.")
            await self.check_balance(db, ent)
            existing = await self._receipt(db, user_id, "end", key, digest)
            if existing is None:
                await self.terminal(db, ent, session, await self.now(db), "ended")
                db.add(
                    VoiceOperation(
                        user_id=user_id,
                        operation="end",
                        request_key=key,
                        request_digest=digest,
                        session_id=session_id,
                    )
                )
            await self.check_balance(db, ent)
            await db.commit()
            return session

    async def read(
        self, user_id: uuid.UUID, session_id: uuid.UUID | None = None, *, turn: bool = False
    ) -> VoiceSession | None:
        if turn:
            self.require_mock(user_id)
        async with self.factory() as db:
            ent = await self.lock_entitlement(db, user_id)
            consent = await self.consented(db, user_id)
            if ent:
                await self.check_balance(db, ent)
                await self.expire_locked(db, ent, await self.now(db), revoked=not consent)
                await self.check_balance(db, ent)
                await db.flush()
            query = select(VoiceSession).where(VoiceSession.user_id == user_id)
            if session_id:
                query = query.where(VoiceSession.id == session_id)
            else:
                query = query.where(VoiceSession.state.in_(OPEN_STATES))
            session = await db.scalar(query.order_by(VoiceSession.created_at.desc()).limit(1))
            await db.commit()
            if session is not None and session.provider != "mock":
                raise HTTPException(503, "Live voice state requires provider reconciliation.")
            if turn and not consent:
                raise HTTPException(403, "Synthetic demo consent is missing or revoked.")
            if session_id and (session is None or (turn and session.state != "active")):
                raise HTTPException(404, "Active voice session not found.")
            return session

    async def entitlement(self, user_id: uuid.UUID) -> dict[str, object]:
        base: dict[str, object] = {
            "enabled": False,
            "provider": self.settings.voice_provider,
            "plan_code": None,
            "minutes_remaining": 0,
            "active_sessions": 0,
            "concurrency_limit": 0,
            "max_call_seconds": 0,
            "live_provider_ready": False,
        }
        if self.settings.voice_provider != "mock" or not self.test_access(user_id):
            return base
        async with self.factory() as db:
            await self._ensure(db, user_id, await self.now(db))
            ent = await self.lock_entitlement(db, user_id)
            assert ent is not None
            now = await self.now(db)
            await self.check_balance(db, ent)
            await self.expire_locked(db, ent, now, revoked=not await self.consented(db, user_id))
            await self.check_balance(db, ent)
            active = await db.scalar(
                select(func.count())
                .select_from(VoiceSession)
                .where(VoiceSession.user_id == user_id, VoiceSession.state.in_(OPEN_STATES))
            )
            if ent.status == "active" and ent.period_start <= now < ent.period_end:
                base.update(
                    enabled=True,
                    plan_code=ent.plan_code,
                    minutes_remaining=(
                        ent.included_seconds - ent.reserved_seconds - ent.consumed_seconds
                    )
                    // 60,
                    active_sessions=int(active or 0),
                    concurrency_limit=ent.concurrency_limit,
                    max_call_seconds=ent.max_call_seconds,
                    prototype_label="Local synthetic demo. No microphone or audio is connected.",
                )
            await db.commit()
            return base
