"""One-shot, buffered exact-report speech behind an independent staging gate.

Lock order: entitlement, session, call/managed operation, identity/consent,
response receipt, release request, report/advisor/publication controls. Provider
I/O is NEVER performed under these locks. A committed send_unknown intent is
never retried; socket delivery/actual provider audio remain external evidence.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.consent import VOICE_REPORT_SPEECH_CONSENT_VERSION
from app.models.db.advisor_review import AdvisorDecision
from app.models.db.consent_record import ConsentRecord
from app.models.db.voice import VoiceSession
from app.models.db.voice_byol_turn import VoiceByolTurn
from app.models.db.voice_case_binding import VoiceCaseBinding
from app.models.db.voice_provider import VoiceProviderCall
from app.voice.byol import SAFE_RESPONSE, BindingDeniedError, ByolTurn, eligible
from app.voice.case_binding import VoiceCaseBindingService, reviewed_caption_packet
from app.voice.service import request_digest

MAX_ANSWER_CHARS = 12000
MAX_TURNS_PER_SESSION = 128
REPORT_READ_REQUESTS = frozenset(
    {
        "read my reviewed report",
        "read the reviewed report",
        "read my report",
        "please read my reviewed report",
    }
)
DISCLOSURE = "I am an AI insurance guide. Here is your independently reviewed report. "


def is_report_read(turn: ByolTurn) -> bool:
    """An explicit allowlist, not intent inference, substring matching or tool dispatch."""
    if not turn.transcript or turn.transcript[-1].role != "user":
        return False
    value = " ".join(turn.transcript[-1].content.strip().lower().split())
    return value.rstrip(".?!") in REPORT_READ_REQUESTS


def turn_digest(turn: ByolTurn) -> str:
    # Fingerprint only the normalized operation; never hash/store chat or overrides.
    return request_digest(
        {
            "operation": "reviewed-report-read-v1",
            "call_id": turn.call_id,
            "response_id": turn.response_id,
            "intent": "report_read" if is_report_read(turn) else "unsupported",
        }
    )


def content_digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TurnTicket:
    id: uuid.UUID
    session_id: uuid.UUID
    owner_id: uuid.UUID
    connection_id: uuid.UUID
    response_id: int
    request_digest: str


@dataclass(frozen=True)
class PreparedAnswer:
    ticket: TurnTicket
    content: str
    content_digest: str
    binding_id: uuid.UUID | None
    report_digest: str | None
    source_digest: str | None
    source_ids: tuple[str, ...]
    expires_at: datetime


@dataclass(frozen=True)
class AuthorizedAnswer:
    frame: dict[str, Any]
    expires_at: datetime


class VoiceByolEvidenceService(VoiceCaseBindingService):
    def evidence_gate(self) -> None:
        if not self.settings.voice_byol_evidence_enabled:
            raise HTTPException(503, "Reviewed voice speech is unavailable.")

    async def _voice_context(
        self,
        db: AsyncSession,
        owner: uuid.UUID,
        session_id: uuid.UUID,
        connection_id: uuid.UUID,
        response_id: int | None = None,
    ) -> tuple[VoiceSession, VoiceProviderCall]:
        self.evidence_gate()
        if not await db.scalar(text("SELECT to_regclass('voice_byol_turns') IS NOT NULL")):
            raise HTTPException(503, "Voice response storage is unavailable.")
        await self._context(db, owner, session_id)
        session = await db.get(VoiceSession, session_id)
        call = await db.get(VoiceProviderCall, session_id)
        # _context already locks entitlement/session/call/managed operation and consents.
        from app.models.db.voice import VoiceEntitlement

        entitlement = await db.scalar(
            select(VoiceEntitlement).where(VoiceEntitlement.user_id == owner)
        )
        if (
            session is None
            or call is None
            or entitlement is None
            or entitlement.provider != "test"
            or entitlement.status != "active"
            or call.byol_connection_id != connection_id
            or call.byol_lease_until is None
            or call.byol_lease_until <= await self.now(db)
            or (response_id is not None and call.last_response_id != response_id)
            or not await eligible(db, session, call, self.settings, self)
        ):
            raise BindingDeniedError()
        return session, call

    @staticmethod
    def _ticket(row: VoiceByolTurn) -> TurnTicket:
        return TurnTicket(
            row.id,
            row.session_id,
            row.owner_id,
            row.connection_id,
            row.response_id,
            row.request_digest,
        )

    async def _row(self, db: AsyncSession, ticket: TurnTicket) -> VoiceByolTurn:
        row = await db.get(VoiceByolTurn, ticket.id, with_for_update=True)
        if row is None or self._ticket(row) != ticket:
            raise BindingDeniedError()
        return row

    async def begin(
        self,
        room: str,
        connection_id: uuid.UUID,
        turn: ByolTurn,
    ) -> TurnTicket | None:
        if turn.call_id != room or turn.interaction_type != "response_required":
            raise BindingDeniedError()
        async with self.factory() as db:
            owner = await db.scalar(
                select(VoiceSession.user_id)
                .join(
                    VoiceProviderCall,
                    VoiceProviderCall.session_id == VoiceSession.id,
                )
                .where(VoiceProviderCall.room == room)
            )
            if owner is None:
                raise BindingDeniedError()
            session_id = await db.scalar(
                select(VoiceProviderCall.session_id).where(VoiceProviderCall.room == room)
            )
            if session_id is None:
                raise BindingDeniedError()
            session, call = await self._voice_context(db, owner, session_id, connection_id)
            prior = await db.scalar(
                select(VoiceByolTurn).where(
                    VoiceByolTurn.session_id == session.id,
                    VoiceByolTurn.response_id == turn.response_id,
                )
            )
            digest = turn_digest(turn)
            if prior is not None:
                if prior.request_digest != digest:
                    raise BindingDeniedError()
                return None  # No response replay, including pending/unknown after a restart.
            if turn.response_id <= call.last_response_id:
                return None
            # Serialize the bounded durable write budget with the existing session lock.
            if (
                int(
                    await db.scalar(
                        select(func.count())
                        .select_from(VoiceByolTurn)
                        .where(
                            VoiceByolTurn.session_id == session.id,
                        )
                    )
                    or 0
                )
                >= MAX_TURNS_PER_SESSION
            ):
                raise BindingDeniedError()
            await db.execute(
                update(VoiceByolTurn)
                .where(
                    VoiceByolTurn.session_id == session.id,
                    VoiceByolTurn.response_id < turn.response_id,
                    VoiceByolTurn.state.in_(("pending", "prepared")),
                )
                .values(state="interrupted")
            )
            call.last_response_id = turn.response_id
            row = VoiceByolTurn(
                id=uuid.uuid4(),
                session_id=session.id,
                owner_id=owner,
                connection_id=connection_id,
                response_id=turn.response_id,
                request_digest=digest,
                intent="report" if is_report_read(turn) else "unsupported",
                state="pending",
            )
            db.add(row)
            await db.flush()
            ticket = self._ticket(row)
            await db.commit()
            return ticket

    async def _answer(
        self,
        db: AsyncSession,
        row: VoiceByolTurn,
        session: VoiceSession,
        call: VoiceProviderCall,
    ) -> PreparedAnswer:
        try:
            return await self._released_answer(db, row, session, call)
        except HTTPException:
            # Current identity, consent and connection were independently checked by
            # _voice_context. Held/unavailable report text never becomes speech.
            assert call.byol_lease_until is not None
            expiry = min(
                session.expires_at,
                call.byol_lease_until,
                await self.now(db) + timedelta(seconds=10),
            )
            return PreparedAnswer(
                self._ticket(row),
                SAFE_RESPONSE,
                content_digest(SAFE_RESPONSE),
                None,
                None,
                None,
                (),
                expiry,
            )

    async def _released_answer(
        self,
        db: AsyncSession,
        row: VoiceByolTurn,
        session: VoiceSession,
        call: VoiceProviderCall,
    ) -> PreparedAnswer:
        assert call.byol_lease_until is not None
        expiry = min(
            session.expires_at, call.byol_lease_until, await self.now(db) + timedelta(seconds=10)
        )
        if row.intent == "unsupported":
            return PreparedAnswer(
                self._ticket(row),
                SAFE_RESPONSE,
                content_digest(SAFE_RESPONSE),
                None,
                None,
                None,
                (),
                expiry,
            )
        # A browser audio grant never authorizes exporting previously private report text.
        # Entitlement is already locked, matching voice-purpose withdrawal lock order.
        report_consent = await db.scalar(
            select(ConsentRecord)
            .where(
                ConsentRecord.user_id == row.owner_id,
                ConsentRecord.scope == "voice_report_speech",
                ConsentRecord.purpose_version == VOICE_REPORT_SPEECH_CONSENT_VERSION,
                ConsentRecord.revoked_at.is_(None),
            )
            .with_for_update(read=True)
        )
        if report_consent is None:
            raise HTTPException(403, "Separate current report-sharing consent required.")
        binding = await db.scalar(
            select(VoiceCaseBinding).where(
                VoiceCaseBinding.voice_session_id == session.id,
                VoiceCaseBinding.owner_id == row.owner_id,
                VoiceCaseBinding.issuer == self.settings.auth_issuer,
            )
        )
        if binding is None:
            raise HTTPException(409, "A currently released reviewed report is required.")
        released = await self._release(db, row.owner_id, binding)
        sentences = reviewed_caption_packet(released["output"])
        spoken = []
        source_ids: list[str] = []
        for sentence in sentences:
            sources = []
            for citation in sentence["citations"]:
                sources.append(
                    f"Source: {citation['source']}. Last verified: {citation['last_verified']}."
                )
                source_ids.append(citation["id"])
                expiry = min(expiry, datetime.fromisoformat(citation["expires_at"]))
            # Preserve the entire original sentence/conditions before naming its evidence.
            spoken.append(sentence["text"] + " " + " ".join(sources))
        content = DISCLOSURE + " ".join(spoken)
        if len(content) > MAX_ANSWER_CHARS:
            raise HTTPException(409, "This report requires the reviewed text companion.")
        event = await db.get(AdvisorDecision, binding.advisor_event_id)
        if event is None or event.expires_at is None:
            raise BindingDeniedError()
        expiry = min(expiry, event.expires_at)
        if expiry <= await self.now(db):
            raise BindingDeniedError()
        return PreparedAnswer(
            self._ticket(row),
            content,
            content_digest(content),
            binding.id,
            binding.report_digest,
            request_digest({"sentences": sentences}),
            tuple(source_ids),
            expiry,
        )

    async def prepare(self, ticket: TurnTicket, turn: ByolTurn) -> PreparedAnswer:
        if turn_digest(turn) != ticket.request_digest:
            raise BindingDeniedError()
        async with self.factory() as db:
            session, call = await self._voice_context(
                db,
                ticket.owner_id,
                ticket.session_id,
                ticket.connection_id,
                ticket.response_id,
            )
            row = await self._row(db, ticket)
            if row.state != "pending":
                raise BindingDeniedError()
            answer = await self._answer(db, row, session, call)
            row.state = "prepared"
            row.answer_kind = "report" if answer.binding_id is not None else "operational"
            row.answer_digest = answer.content_digest
            row.source_digest = answer.source_digest
            row.binding_id = answer.binding_id
            row.authorization_expires_at = answer.expires_at
            row.prepared_at = await self.now(db)
            await db.commit()
            return answer

    async def authorize_send(self, prepared: PreparedAnswer) -> AuthorizedAnswer:
        ticket = prepared.ticket
        async with self.factory() as db:
            session, call = await self._voice_context(
                db,
                ticket.owner_id,
                ticket.session_id,
                ticket.connection_id,
                ticket.response_id,
            )
            row = await self._row(db, ticket)
            if (
                row.state != "prepared"
                or row.answer_digest != prepared.content_digest
                or row.answer_digest != content_digest(prepared.content)
                or row.source_digest != prepared.source_digest
                or row.binding_id != prepared.binding_id
                or row.authorization_expires_at is None
                or row.authorization_expires_at != prepared.expires_at
                or prepared.expires_at <= await self.now(db)
            ):
                raise BindingDeniedError()
            fresh = await self._answer(db, row, session, call)
            if (
                fresh.content != prepared.content
                or fresh.content_digest != row.answer_digest
                or fresh.source_digest != row.source_digest
                or fresh.binding_id != row.binding_id
                or fresh.report_digest != prepared.report_digest
                or fresh.source_ids != prepared.source_ids
            ):
                raise BindingDeniedError()
            # Durable BEFORE network I/O: a timeout/crash is unknown, never unsent/replayed.
            row.state = "send_unknown"
            row.attempted_at = await self.now(db)
            deadline = min(
                prepared.expires_at, fresh.expires_at, row.attempted_at + timedelta(seconds=2)
            )
            packet = AuthorizedAnswer(
                {
                    "response_type": "response",
                    "response_id": ticket.response_id,
                    "content": prepared.content,
                    "content_complete": True,
                },
                deadline,
            )
            await db.commit()
            return packet

    async def complete(self, ticket: TurnTicket) -> bool:
        """Record socket-send return only; NOT TTS delivery, termination or usage proof."""
        async with self.factory() as db:
            await self._voice_context(
                db,
                ticket.owner_id,
                ticket.session_id,
                ticket.connection_id,
                ticket.response_id,
            )
            row = await self._row(db, ticket)
            if row.state != "send_unknown":
                return False
            row.state = "sent"
            row.completed_at = await self.now(db)
            await db.commit()
            return True

    async def interrupt(self, room: str, connection_id: uuid.UUID, new_response_id: int) -> None:
        """Internal newer-response fence; no undocumented provider interrupt frame."""
        async with self.factory() as db:
            call = await db.scalar(select(VoiceProviderCall).where(VoiceProviderCall.room == room))
            if call is None:
                raise BindingDeniedError()
            session = await db.get(VoiceSession, call.session_id)
            assert session is not None
            await self._voice_context(db, session.user_id, session.id, connection_id)
            if not 1 <= new_response_id <= 2147483647:
                raise BindingDeniedError()
            await db.execute(
                update(VoiceByolTurn)
                .where(
                    VoiceByolTurn.session_id == session.id,
                    VoiceByolTurn.response_id < new_response_id,
                    VoiceByolTurn.state.in_(("pending", "prepared")),
                )
                .values(state="interrupted")
            )
            await db.commit()
