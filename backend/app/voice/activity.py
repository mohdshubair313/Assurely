"""Derived response receipts, never a transcript or proof of audible delivery.

All reads share one entitlement-first transaction with current identity, consent,
frozen case binding and the existing independent human release authority.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.consent import CONSENT_VERSION, VOICE_CONSENT_VERSION
from app.models.db.advisor_review import AdvisorDecision
from app.models.db.auth_identity import AuthIdentity
from app.models.db.consent_record import ConsentRecord
from app.models.db.voice_byol_turn import VoiceByolTurn
from app.models.db.voice_case_binding import VoiceCaseBinding
from app.voice.case_binding import VoiceCaseBindingService, reviewed_caption_packet
from app.voice.service import request_digest

MAX_ACTIVITY_EVENTS = 128
ACTIVITY_STATUS = {
    "pending": "pending",
    "prepared": "pending",
    "send_unknown": "delivery_uncertain",
    "sent": "response_sent",
    "interrupted": "interrupted",
    "failed": "failed",
}


class ActivityRecapService(VoiceCaseBindingService):
    async def authorize_summary(self, db: AsyncSession, owner: uuid.UUID) -> None:
        """Entitlement must already be locked; microphone consent is unrelated."""
        self.binding_gate(owner)
        identity = await db.scalar(
            select(AuthIdentity)
            .where(
                AuthIdentity.user_id == owner,
                AuthIdentity.provider == "clerk",
                AuthIdentity.issuer == self.settings.auth_issuer,
                AuthIdentity.disabled.is_(False),
            )
            .with_for_update(read=True)
        )
        grants = (
            await db.scalars(
                select(ConsentRecord)
                .where(
                    ConsentRecord.user_id == owner,
                    ConsentRecord.revoked_at.is_(None),
                    ConsentRecord.scope.in_(("process_comparison", "voice_summary")),
                )
                .order_by(ConsentRecord.scope, ConsentRecord.id)
                .with_for_update(read=True)
            )
        ).all()
        current = {(row.scope, row.purpose_version) for row in grants}
        if identity is None or not {
            ("process_comparison", CONSENT_VERSION),
            ("voice_summary", VOICE_CONSENT_VERSION),
        } <= current:
            raise HTTPException(403, "Current identity, case and separate recap consent required.")

    async def read_activity(self, owner: uuid.UUID, session_id: uuid.UUID) -> dict[str, Any]:
        self.binding_gate(owner)
        async with self.factory() as db:
            if not await db.scalar(text("SELECT to_regclass('voice_byol_turns') IS NOT NULL")):
                raise HTTPException(503, "Voice activity is unavailable on this schema.")
            _, session, call, _ = await self.locked(db, owner, session_id)
            if call is None or not call.synthetic:
                raise HTTPException(404, "Development voice activity not found.")
            await self.authorize_summary(db, owner)
            rows = (
                await db.scalars(
                    select(VoiceByolTurn)
                    .where(VoiceByolTurn.session_id == session_id, VoiceByolTurn.owner_id == owner)
                    .order_by(VoiceByolTurn.response_id)
                    .limit(MAX_ACTIVITY_EVENTS + 1)
                    .with_for_update(read=True)
                )
            ).all()
            if len(rows) > MAX_ACTIVITY_EVENTS:
                raise HTTPException(409, "Voice activity requires operator review.")
            events = []
            for row in rows:
                if (
                    row.state not in ACTIVITY_STATUS
                    or row.intent not in ("report", "unsupported")
                    or row.answer_kind not in (None, "report", "operational")
                ):
                    raise HTTPException(409, "Voice activity integrity check failed.")
                events.append(
                    {
                        "response_id": row.response_id,
                        "intent": "report_read" if row.intent == "report" else "unsupported",
                        "status": ACTIVITY_STATUS[row.state],
                        "answer_kind": row.answer_kind,
                        "created_at": row.created_at.isoformat(),
                        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                    }
                )
            now = await self.now(db)
            expiry = now + timedelta(seconds=10)
            packet: dict[str, Any] | None = None
            availability = "not_sent"
            sent = [row for row in rows if row.state == "sent" and row.answer_kind == "report"]
            if sent:
                availability = "unavailable"
                binding = await db.scalar(
                    select(VoiceCaseBinding).where(
                        VoiceCaseBinding.voice_session_id == session_id,
                        VoiceCaseBinding.issuer == self.settings.auth_issuer,
                        VoiceCaseBinding.owner_id == owner,
                    )
                )
                if binding is not None:
                    try:
                        released = await self._release(db, owner, binding)
                        sentences = reviewed_caption_packet(released["output"])
                        source_digest = request_digest({"sentences": sentences})
                        if not any(
                            row.binding_id == binding.id
                            and row.intent == "report"
                            and row.source_digest == source_digest
                            for row in sent
                        ):
                            raise HTTPException(409, "The report response evidence changed.")
                        event = await db.get(AdvisorDecision, binding.advisor_event_id)
                        if event is None or event.expires_at is None:
                            raise HTTPException(409, "Current independent review is unavailable.")
                        expiry = min(
                            expiry,
                            event.expires_at,
                            *(
                                datetime.fromisoformat(citation["expires_at"])
                                for sentence in sentences
                                for citation in sentence["citations"]
                            ),
                        )
                        packet = {
                            "binding_id": str(binding.id),
                            "case_id": str(binding.case_id),
                            "turn_id": str(binding.turn_id),
                            "report_digest": binding.report_digest,
                            "authorized_at": (await self.now(db)).isoformat(),
                            "display_expires_at": expiry.isoformat(),
                            "sentences": sentences,
                        }
                        availability = "available"
                    except HTTPException as exc:
                        if exc.status_code not in (403, 404, 409):
                            raise
                        # Receipt metadata remains useful; a hold never becomes report text.
                        packet = None
            generated = await self.now(db)
            if expiry <= generated:
                raise HTTPException(409, "Voice activity display authorization expired.")
            result = {
                "kind": "voice_session_activity_recap",
                "voice_session_id": str(session_id),
                "session_state": session.state,
                "generated_at": generated.isoformat(),
                "display_expires_at": expiry.isoformat(),
                "transcript_stored": False,
                "audio_delivery_verified": False,
                "events": events,
                "reviewed_report": packet,
                "report_availability": availability,
            }
            await db.commit()
            return result
