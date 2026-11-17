"""Optional encrypted report excerpts, not generated conversation summaries or transcripts."""

import json
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import exists, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.consent import VOICE_CONSENT_VERSION
from app.db import report_release
from app.db.policy_review_store import WorkflowError
from app.models.db.advisor_review import AdvisorDecision
from app.models.db.consent_record import ConsentRecord
from app.models.db.voice_lifecycle import VoiceRecap
from app.voice.activity import ActivityRecapService
from app.voice.case_binding import reviewed_caption_packet


class RecapService(ActivityRecapService):
    async def summary_consent(self, db: AsyncSession, owner: uuid.UUID) -> bool:
        # Kept for compatibility with callers; full authorization also checks identity
        # and insurance-processing consent in the transaction performing the action.
        return bool(
            await db.scalar(
                select(ConsentRecord.id)
                .where(
                    ConsentRecord.user_id == owner,
                    ConsentRecord.scope == "voice_summary",
                    ConsentRecord.purpose_version == VOICE_CONSENT_VERSION,
                    ConsentRecord.revoked_at.is_(None),
                )
                .with_for_update(read=True)
            )
        )

    async def _storage(self, db: AsyncSession) -> None:
        if not await db.scalar(
            text(
                "SELECT to_regclass('voice_recaps') IS NOT NULL "
                "AND to_regclass('voice_case_bindings') IS NOT NULL"
            )
        ):
            raise HTTPException(503, "Recap storage is not available on this schema.")

    async def _packet(
        self, db: AsyncSession, owner: uuid.UUID, case_id: uuid.UUID, request_key: uuid.UUID
    ) -> tuple[dict[str, Any], datetime]:
        """Current exact reviewed report under the caller's entitlement/consent locks."""
        issuer = self.settings.auth_issuer
        key = uuid.uuid5(
            uuid.NAMESPACE_URL, f"assurely:recap-release:{issuer}:{owner}:{request_key}"
        )
        # Preserve release's request-key -> report-head order before selecting a version.
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"release:{issuer}:{owner}:{key}"},
        )
        try:
            head = await report_release.head(db, issuer, str(case_id), owner)
            if not head.report_digest:
                raise HTTPException(409, "A current independently reviewed report is required.")
            result = await report_release.release(
                db,
                issuer,
                str(case_id),
                owner,
                report_release.ReleaseCommand(
                    request_key=key, turn_id=head.turn_id, report_digest=head.report_digest
                ),
                self._advisors(),
            )
        except WorkflowError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        sentences = reviewed_caption_packet(result["output"])
        event = await db.get(
            AdvisorDecision, uuid.UUID(result["release_receipt"]["advisor_event_id"])
        )
        if event is None or event.expires_at is None:
            raise HTTPException(409, "Current independent review is unavailable.")
        expiry = min(
            event.expires_at,
            *(datetime.fromisoformat(c["expires_at"]) for s in sentences for c in s["citations"]),
        )
        if expiry <= await self.now(db):
            raise HTTPException(409, "Report display authorization expired.")
        return {
            "case_id": str(case_id),
            "report_digest": head.report_digest,
            "sentences": sentences,
            "speech": " ".join(sentence["text"] for sentence in sentences),
            "generated_by": "existing_explanation_report",
            "new_calculation": False,
            "human_approval_granted": False,
        }, expiry

    async def create_recap(
        self, owner: uuid.UUID, case_id: uuid.UUID, key: uuid.UUID
    ) -> dict[str, Any]:
        self.binding_gate(owner)
        async with self.factory() as db:
            await self._storage(db)
            await self.lock_entitlement(db, owner)
            await self.authorize_summary(db, owner)
            # Also serialize owners without an existing voice entitlement row.
            await db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"voice-recap:{owner}:{key}"},
            )
            row = await db.scalar(
                select(VoiceRecap)
                .where(VoiceRecap.user_id == owner, VoiceRecap.request_key == key)
                .with_for_update()
            )
            now = await self.now(db)
            if row is not None:
                if row.case_id != case_id:
                    raise HTTPException(409, "Recap key was used for another report version.")
                if row.encrypted_content is None or row.expires_at <= now:
                    raise HTTPException(404, "Recap was deleted or expired.")
            packet, _ = await self._packet(db, owner, case_id, key)
            if row is not None:
                if row.report_digest != packet["report_digest"]:
                    raise HTTPException(409, "Recap key was used for another report version.")
            else:
                row = VoiceRecap(
                    user_id=owner,
                    case_id=case_id,
                    request_key=key,
                    report_digest=packet["report_digest"],
                    encrypted_content=self.cipher().encrypt(json.dumps(packet).encode()).decode(),
                    expires_at=now + timedelta(hours=self.settings.voice_summary_retention_hours),
                )
                db.add(row)
                await db.flush()
            result = {
                "recap_id": str(row.id),
                "kind": "validated_report_excerpt",
                "expires_at": row.expires_at.isoformat(),
                "transcript_stored": False,
            }
            await db.commit()
            return result

    async def read_recap(self, owner: uuid.UUID, recap_id: uuid.UUID) -> dict[str, Any]:
        self.binding_gate(owner)
        async with self.factory() as db:
            await self._storage(db)
            await self.lock_entitlement(db, owner)
            await self.authorize_summary(db, owner)
            row = await db.scalar(
                select(VoiceRecap)
                .where(VoiceRecap.user_id == owner, VoiceRecap.id == recap_id)
                .with_for_update()
            )
            if row is None or not row.encrypted_content or row.expires_at <= await self.now(db):
                raise HTTPException(404, "Recap not found or expired.")
            packet, evidence_expiry = await self._packet(db, owner, row.case_id, row.request_key)
            if packet["report_digest"] != row.report_digest:
                raise HTTPException(409, "Report changed; the saved excerpt cannot be released.")
            expiry = min(
                row.expires_at, evidence_expiry, await self.now(db) + timedelta(seconds=10)
            )
            if expiry <= await self.now(db):
                raise HTTPException(409, "Recap display authorization expired.")
            result = {
                "kind": "validated_report_excerpt",
                **packet,
                "display_expires_at": expiry.isoformat(),
            }
            await db.commit()
            return result

    async def delete_recap(self, owner: uuid.UUID, recap_id: uuid.UUID) -> dict[str, Any]:
        async with self.factory() as db:
            if not await db.scalar(text("SELECT to_regclass('voice_recaps')")):
                raise HTTPException(503, "Recap storage is not available on this schema.")
            await self.lock_entitlement(db, owner)
            row = await db.scalar(
                select(VoiceRecap)
                .where(VoiceRecap.user_id == owner, VoiceRecap.id == recap_id)
                .with_for_update()
            )
            if not row:
                raise HTTPException(404, "Recap not found.")
            row.encrypted_content = None
            await db.commit()
        return {"deleted": True}


async def prune_recaps(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as db:
        active_consent = exists(
            select(ConsentRecord.id).where(
                ConsentRecord.user_id == VoiceRecap.user_id,
                ConsentRecord.scope == "voice_summary",
                ConsentRecord.purpose_version == VOICE_CONSENT_VERSION,
                ConsentRecord.revoked_at.is_(None),
            )
        )
        from sqlalchemy import func, or_

        await db.execute(
            update(VoiceRecap)
            .where(
                VoiceRecap.encrypted_content.is_not(None),
                or_(VoiceRecap.expires_at <= func.now(), ~active_consent),
            )
            .values(encrypted_content=None)
        )
        await db.commit()
