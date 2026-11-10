"""Durable synthetic managed calls. Unknown external effects retain reservations.

Locks: entitlement -> session -> provider binding -> managed operation. Network I/O
always happens after committing the operation intent and releasing these locks.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.consent import VOICE_CONSENT_VERSION
from app.models.db.auth_identity import AuthIdentity
from app.models.db.consent_record import ConsentRecord
from app.models.db.voice import VoiceEntitlement, VoiceOperation, VoiceSession
from app.models.db.voice_lifecycle import VoiceFundingAllocation, VoiceManagedOperation
from app.models.db.voice_provider import VoiceProviderCall
from app.voice.managed_provider import ManagedVaaniProvider
from app.voice.service import OPEN_STATES, VoiceSessionService, request_digest
from app.voice.vaani import VaaniError


class ManagedVoiceService(VoiceSessionService):
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        provider: ManagedVaaniProvider | None = None,
    ) -> None:
        super().__init__(factory, settings)
        self.provider = provider or ManagedVaaniProvider(settings)

    def cipher(self) -> Fernet:
        try:
            return Fernet(self.settings.voice_token_encryption_key.get_secret_value().encode())
        except (ValueError, TypeError):
            raise HTTPException(503, "Voice credential encryption is unavailable.") from None

    def gate(self, owner: uuid.UUID) -> None:
        cfg = self.settings
        if not (
            cfg.voice_development_enabled
            and cfg.environment in ("development", "staging")
            and cfg.vaani_dispatch_enabled
            and cfg.vaani_byol_enabled
            and cfg.vaani_ingress_enabled
            and cfg.vaani_dev_agent_reviewed
            and self.test_access(owner)
        ):
            raise HTTPException(503, "Synthetic development audio is unavailable.")
        self.cipher()
        try:
            uuid.UUID(cfg.vaani_agent_id)
            origin = urlsplit(cfg.vaani_staging_base_url)
            if (
                not cfg.vaani_api_key.get_secret_value()
                or len(cfg.vaani_byol_token.get_secret_value()) < 32
                or len(cfg.vaani_webhook_secret.get_secret_value()) < 32
                or origin.scheme != "https"
                or not origin.hostname
                or origin.username
                or origin.password
                or origin.query
                or origin.fragment
                or origin.path not in ("", "/")
            ):
                raise ValueError()
        except ValueError:
            raise HTTPException(503, "Development provider configuration is incomplete.") from None

    async def consent(self, db: AsyncSession, owner: uuid.UUID) -> bool:
        scopes = set(
            (
                await db.scalars(
                    select(ConsentRecord.scope).where(
                        ConsentRecord.user_id == owner,
                        ConsentRecord.revoked_at.is_(None),
                        ConsentRecord.purpose_version == VOICE_CONSENT_VERSION,
                    )
                )
            ).all()
        )
        identity = await db.scalar(
            select(AuthIdentity.id).where(
                AuthIdentity.user_id == owner,
                AuthIdentity.issuer == self.settings.auth_issuer,
                AuthIdentity.provider == "clerk",
                AuthIdentity.disabled.is_(False),
            )
        )
        return bool(identity and {"voice_microphone", "voice_vendor_processing"} <= scopes)

    async def reserve(self, owner: uuid.UUID, key: uuid.UUID) -> tuple[VoiceSession, bool]:
        self.gate(owner)
        digest = request_digest({"language": "en", "mode": "managed-synthetic"})
        async with self.factory() as db:
            await self._ensure(db, owner, await self.now(db))
            ent = await self.lock_entitlement(db, owner)
            now = await self.now(db)
            assert ent is not None
            await self.check_balance(db, ent)
            if not await self.consent(db, owner):
                raise HTTPException(
                    403, "Current microphone and vendor processing consent required."
                )
            prior = await self._receipt(db, owner, "start", key, digest)
            if prior:
                return prior, False
            active = await db.scalar(
                select(func.count())
                .select_from(VoiceSession)
                .where(VoiceSession.user_id == owner, VoiceSession.state.in_(OPEN_STATES))
            )
            cap = min(ent.max_call_seconds, self.settings.voice_max_call_seconds)
            from app.voice.funding import allocate_period

            funding_id = await allocate_period(db, ent, self.settings, now, cap)
            if (
                ent.provider != "test"
                or ent.status != "active"
                or (funding_id is None and not ent.period_start <= now < ent.period_end)
                or cap < 60
                or ent.included_seconds - ent.reserved_seconds - ent.consumed_seconds < cap
            ):
                raise HTTPException(402, "No sufficient development allowance is available.")
            if int(active or 0) >= ent.concurrency_limit:
                raise HTTPException(409, "A voice session is already open.")
            session = VoiceSession(
                id=uuid.uuid4(),
                user_id=owner,
                provider="vaani",
                state="reserved",
                language="en",
                idempotency_key=key,
                request_digest=digest,
                expires_at=now + timedelta(seconds=cap),
                recovery_after=now + timedelta(seconds=45),
                reserved_seconds=cap,
                consumed_seconds=0,
                consent_snapshot={"version": VOICE_CONSENT_VERSION, "synthetic": True},
                source_mode="synthetic-vaani",
                trace_id=uuid.uuid4().hex,
                created_at=now,
            )
            db.add(session)
            await db.flush()
            if funding_id is not None:
                db.add(VoiceFundingAllocation(session_id=session.id, period_id=funding_id))
            ent.reserved_seconds += cap
            self._entry(db, ent, session, "reservation", cap)
            db.add(
                VoiceOperation(
                    user_id=owner,
                    operation="start",
                    request_key=key,
                    request_digest=digest,
                    session_id=session.id,
                )
            )
            db.add(
                VoiceManagedOperation(
                    session_id=session.id, phase="pending_create", end_requested=False
                )
            )
            await self.check_balance(db, ent)
            await db.commit()
            return session, True

    async def locked(
        self, db: AsyncSession, owner: uuid.UUID, session_id: uuid.UUID
    ) -> tuple[VoiceEntitlement, VoiceSession, VoiceProviderCall | None, VoiceManagedOperation]:
        ent = await self.lock_entitlement(db, owner)
        session = await db.scalar(
            select(VoiceSession)
            .where(VoiceSession.id == session_id, VoiceSession.user_id == owner)
            .with_for_update()
        )
        if not session or session.source_mode != "synthetic-vaani":
            raise HTTPException(404, "Development voice session not found.")
        call = await db.scalar(
            select(VoiceProviderCall)
            .where(VoiceProviderCall.session_id == session_id)
            .with_for_update()
        )
        operation = await db.get(VoiceManagedOperation, session_id, with_for_update=True)
        if not ent or not operation:
            raise HTTPException(503, "Voice operation requires reconciliation.")
        await self.check_balance(db, ent)
        return ent, session, call, operation

    async def view(
        self, owner: uuid.UUID, session_id: uuid.UUID, *, material: bool = False
    ) -> dict[str, Any]:
        async with self.factory() as db:
            _, session, call, op = await self.locked(db, owner, session_id)
            now = await self.now(db)
            allowed = bool(
                self.settings.voice_development_enabled
                and self.settings.vaani_byol_enabled
                and self.settings.vaani_dev_agent_reviewed
                and self.test_access(owner)
                and session.state in OPEN_STATES
                and session.expires_at > now
                and not op.end_requested
                and op.phase == "connected"
                and call
                and call.phase in ("ready", "active")
                and await self.consent(db, owner)
            )
            result = {
                "session_id": str(session.id),
                "phase": op.phase,
                "state": session.state,
                "room_name": call.room if call else None,
                "allowed": allowed,
                "synthetic": True,
                "reserved_seconds": session.reserved_seconds,
                "consumed_seconds": session.consumed_seconds,
                "expires_at": min(session.expires_at, now + timedelta(seconds=60)).isoformat(),
                "end_requested": op.end_requested,
            }
            if material:
                if not allowed or not op.encrypted_connection:
                    raise HTTPException(
                        409, "Audio connection is not available; inspect session status."
                    )
                try:
                    connection = json.loads(self.cipher().decrypt(op.encrypted_connection.encode()))
                except (InvalidToken, ValueError):
                    raise HTTPException(503, "Voice credential recovery is unavailable.") from None
                result.update(url=connection["lk_url"], token=connection["lk_token"])
            return result

    async def request_end(self, owner: uuid.UUID, session_id: uuid.UUID) -> dict[str, Any]:
        async with self.factory() as db:
            _, session, call, op = await self.locked(db, owner, session_id)
            op.end_requested = True
            if call and session.state in OPEN_STATES:
                call.phase = "termination_required"
            await db.commit()
        return await self.view(owner, session_id)

    async def advance(
        self, owner: uuid.UUID, session_id: uuid.UUID, *, connect: bool = False
    ) -> None:
        """Claim exactly one durable external operation. No unknown create/connect redispatch."""
        async with self.factory() as db:
            ent, session, call, op = await self.locked(db, owner, session_id)
            now = await self.now(db)
            if session.state not in OPEN_STATES:
                # Trusted signed events settle usage; discard recoverable media credentials.
                op.encrypted_connection = op.encrypted_token = None
                op.phase = "ended"
                await db.commit()
                return
            if op.lease_until and op.lease_until > now:
                return
            if op.phase in ("creating", "connecting"):
                op.phase = "start_unknown"
                op.error_category = "interrupted_operation"
            if op.phase == "binding":
                op.phase = "created"  # A status read is safe to resume after its lease expires.
            if session.expires_at <= now or not await self.consent(db, owner):
                op.end_requested = True
            if (
                not self.settings.voice_development_enabled
                or not self.settings.vaani_byol_enabled
                or not self.settings.vaani_dev_agent_reviewed
                or not self.test_access(owner)
            ):
                op.end_requested = True
            if call and call.phase in ("termination_required", "reconciling"):
                op.end_requested = True
            if op.end_requested:
                if op.phase == "pending_create":
                    # No external intent has been claimed, so no call can exist.
                    ent.reserved_seconds -= session.reserved_seconds
                    session.state, session.ended_at = "failed", now
                    self._entry(db, ent, session, "settlement", 0)
                    self._entry(db, ent, session, "release", session.reserved_seconds)
                    op.phase = "ended"
                    await self.check_balance(db, ent)
                    await db.commit()
                    return
                if not op.encrypted_token or op.phase == "awaiting_usage":
                    await db.commit()
                    return
                action = "terminating"
                if call:
                    call.phase = "termination_required"
            elif op.phase == "pending_create":
                self.gate(owner)
                action = "creating"
            elif op.phase == "created":
                action = "binding"
            elif op.phase == "ready" and connect:
                self.gate(owner)
                action = "connecting"
            else:
                await db.commit()
                return
            op.phase, op.lease_until = action, now + timedelta(seconds=45)
            encrypted = op.encrypted_token
            cap = int((session.expires_at - now).total_seconds())
            if action == "creating" and cap < 60:
                op.phase, op.end_requested, op.lease_until = "pending_create", True, None
                await db.commit()
                return
            await db.commit()
        # Unknown outcomes retain the committed reservation and operation receipt.
        try:
            result: Any
            token = (
                SecretStr(self.cipher().decrypt(encrypted.encode()).decode()) if encrypted else None
            )
            if action == "creating":
                result = await self.provider.create(session_id, min(cap, 1800))
            elif action == "binding":
                assert token is not None
                result = await self.provider.status(token)
            elif action == "connecting":
                assert token is not None
                result = await self.provider.connect(token)
            else:
                assert token is not None
                result = await self.provider.terminate(token)
            async with self.factory() as db:
                _, session, call, op = await self.locked(db, owner, session_id)
                if op.phase != action:
                    return
                if session.state not in OPEN_STATES:
                    op.encrypted_token = op.encrypted_connection = None
                    op.phase, op.lease_until = "ended", None
                    await db.commit()
                    return
                if action == "creating":
                    op.encrypted_token = (
                        self.cipher()
                        .encrypt(result.session_token.get_secret_value().encode())
                        .decode()
                    )
                    # Provider expiry is an upper bound, never a reason to extend reservation.
                    session.expires_at = min(session.expires_at, result.expires_at)
                    op.phase = "created"
                elif action == "binding":
                    if result.status not in ("created", "agent_ready"):
                        raise VaaniError("unexpected_managed_state")
                    if call is None:
                        db.add(
                            VoiceProviderCall(
                                session_id=session_id,
                                room=result.room_name,
                                agent_id=result.agent_id,
                                synthetic=True,
                                phase="ready",
                                last_response_id=0,
                            )
                        )
                        session.provider_call_id = session.room_id = result.room_name
                    elif call.room != result.room_name:
                        raise VaaniError("room_mismatch")
                    op.phase = "ready"
                elif action == "connecting":
                    if not call or call.room != result.room_name:
                        raise VaaniError("room_mismatch")
                    op.encrypted_connection = (
                        self.cipher()
                        .encrypt(
                            json.dumps(
                                {
                                    "lk_url": result.lk_url,
                                    "lk_token": result.lk_token.get_secret_value(),
                                }
                            ).encode()
                        )
                        .decode()
                    )
                    op.phase = "connected"
                else:
                    if call and result.room_name != call.room:
                        raise VaaniError("room_mismatch")
                    op.phase = "awaiting_usage"
                    op.encrypted_connection = None
                op.lease_until = None
                op.updated_at = await self.now(db)
                await db.commit()
        except Exception:
            # No exception bodies/URLs/tokens are logged or returned.
            async with self.factory() as db:
                _, _, _, op = await self.locked(db, owner, session_id)
                if op.phase == action:
                    op.phase = (
                        "start_unknown"
                        if action in ("creating", "connecting")
                        else ("created" if action == "binding" else "termination_unknown")
                    )
                    op.error_category = "provider_operation_unconfirmed"
                    op.lease_until = await self.now(db) + timedelta(seconds=30)
                    await db.commit()


async def recover_managed(factory: async_sessionmaker[AsyncSession], settings: Settings) -> int:
    """Restarts preserve unknown operations. Never infer zero usage from an ended token."""
    service = ManagedVoiceService(factory, settings)
    async with factory() as db:
        # Compatibility with the still-running 013 application during an additive rollout.
        if not await db.scalar(text("SELECT to_regclass('voice_managed_operations')")):
            return 0
        hints = (
            await db.execute(
                select(VoiceSession.id, VoiceSession.user_id)
                .join(VoiceManagedOperation, VoiceManagedOperation.session_id == VoiceSession.id)
                .where(VoiceManagedOperation.phase != "ended")
                .order_by(VoiceManagedOperation.updated_at)
                .limit(100)
            )
        ).all()
    for session_id, owner in hints:
        await service.advance(owner, session_id)
    from app.voice.recaps import prune_recaps

    await prune_recaps(factory)
    return len(hints)
