"""Optional encrypted report excerpts, not generated conversation summaries or transcripts."""

import json
import uuid
from datetime import timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import exists, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.consent import VOICE_CONSENT_VERSION
from app.models.db.consent_record import ConsentRecord
from app.models.db.voice_lifecycle import VoiceRecap
from app.voice.evidence import current_packet
from app.voice.managed import ManagedVoiceService


class RecapService(ManagedVoiceService):
    async def summary_consent(self, db: AsyncSession, owner: uuid.UUID) -> bool:
        return bool(
            await db.scalar(
                select(ConsentRecord.id)
                .where(
                    ConsentRecord.user_id == owner,
                    ConsentRecord.scope == "voice_summary",
                    ConsentRecord.purpose_version == VOICE_CONSENT_VERSION,
                    ConsentRecord.revoked_at.is_(None),
                )
                .with_for_update()
            )
        )

    async def create_recap(
        self, owner: uuid.UUID, case_id: uuid.UUID, key: uuid.UUID
    ) -> dict[str, Any]:
        packet = await current_packet(self.factory, self.settings, owner, case_id)
        async with self.factory() as db:
            await self.lock_entitlement(db, owner)
            if not await self.summary_consent(db, owner):
                raise HTTPException(403, "Separate current recap storage consent is required.")
            row = await db.scalar(
                select(VoiceRecap)
                .where(VoiceRecap.user_id == owner, VoiceRecap.request_key == key)
                .with_for_update()
            )
            if row:
                if row.case_id != case_id or row.report_digest != packet["report_digest"]:
                    raise HTTPException(409, "Recap key was used for another report version.")
            else:
                row = VoiceRecap(
                    user_id=owner,
                    case_id=case_id,
                    request_key=key,
                    report_digest=packet["report_digest"],
                    encrypted_content=self.cipher().encrypt(json.dumps(packet).encode()).decode(),
                    expires_at=await self.now(db)
                    + timedelta(hours=self.settings.voice_summary_retention_hours),
                )
                db.add(row)
            await db.commit()
            return {
                "recap_id": str(row.id),
                "kind": "validated_report_excerpt",
                "expires_at": row.expires_at.isoformat(),
                "transcript_stored": False,
            }

    async def read_recap(self, owner: uuid.UUID, recap_id: uuid.UUID) -> dict[str, Any]:
        if not self.settings.voice_tools_enabled:
            raise HTTPException(503, "Voice evidence tools are unavailable.")
        async with self.factory() as db:
            await self.lock_entitlement(db, owner)
            if not await self.summary_consent(db, owner):
                raise HTTPException(403, "Recap consent is absent or withdrawn.")
            row = await db.scalar(
                select(VoiceRecap).where(VoiceRecap.user_id == owner, VoiceRecap.id == recap_id)
            )
            if not row or not row.encrypted_content or row.expires_at <= await self.now(db):
                raise HTTPException(404, "Recap not found or expired.")
            case_id, digest = row.case_id, row.report_digest
        # Saved excerpts cannot bypass later holds, changed evidence or source revocation.
        packet = await current_packet(self.factory, self.settings, owner, case_id)
        if packet["report_digest"] != digest:
            raise HTTPException(409, "Report changed; the saved excerpt cannot be released.")
        return {"kind": "validated_report_excerpt", **packet}

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
