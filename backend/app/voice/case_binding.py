"""Immutable reviewed-case selection with transaction-local display authorization.

Locks: entitlement -> voice session -> provider/operation -> identity/consent ->
binding request -> release request -> report head -> advisor/publication controls.
No network, graph mutation, provider speech, or permanent release grant occurs here.
"""

from __future__ import annotations

import copy
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.consent import CONSENT_VERSION
from app.db import report_release
from app.db.policy_review_store import WorkflowError
from app.db.source_review import ClosedModel
from app.models.db.advisor_review import AdvisorDecision
from app.models.db.auth_identity import AuthIdentity
from app.models.db.consent_record import ConsentRecord
from app.models.db.voice_case_binding import VoiceCaseBinding
from app.voice.evidence import speech_packet
from app.voice.managed import ManagedVoiceService
from app.voice.service import OPEN_STATES, request_digest


class BindCaseCommand(ClosedModel):
    case_id: uuid.UUID
    idempotency_key: uuid.UUID


def _url(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 4096
        or any(c.isspace() or ord(c) < 32 or ord(c) == 127 or c == "\\" for c in value)
    ):
        raise HTTPException(409, "A source reference is unavailable.")
    try:
        parsed = urlsplit(value)
        # Accessing .port validates malformed and out-of-range ports; urlsplit alone does not.
        port = parsed.port
    except ValueError:
        raise HTTPException(409, "A source reference is unavailable.") from None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or port == 0
    ):
        raise HTTPException(409, "A source reference is unavailable.")
    return value


def _references(value: Any, *, allow_empty: bool = False) -> list[dict[str, Any]]:
    from app.db.source_review import Reference

    if not isinstance(value, list) or not (0 if allow_empty else 1) <= len(value) <= 20:
        raise HTTPException(409, "Source references are unavailable.")
    result = []
    for item in value:
        try:
            ref = Reference.model_validate({k: item[k] for k in Reference.model_fields})
            digest = item["sha256"]
            if not isinstance(digest, str) or len(digest) != 64:
                raise ValueError()
            int(digest, 16)
            result.append({**ref.model_dump(), "url": _url(item["url"]), "sha256": digest})
        except (KeyError, TypeError, ValueError):
            raise HTTPException(409, "A source reference is unavailable.") from None
    return result


def reviewed_caption_packet(output: dict[str, Any]) -> list[dict[str, Any]]:
    """Project an already transactionally released report; not an authorization API."""
    # Validate text/date/compliance without rewriting the immutable report status.
    validated = speech_packet({**output, "report_status": "ready"})
    if output.get("report_status") != "reviewed_report_held":
        raise HTTPException(409, "A reviewed report is required.")
    rows = []
    for index, (original, normalized) in enumerate(
        zip(output["sentences"], validated["sentences"], strict=True)
    ):
        sources = []
        for citation, basic in zip(original["citations"], normalized["citations"], strict=True):
            try:
                sources.append(
                    {
                        **basic,
                        "id": citation["id"],
                        "url": _url(citation["url"]),
                        "expires_at": citation["expires_at"],
                        "references": _references(citation["references"]),
                        "applicability_evidence": _references(
                            citation["applicability_evidence"], allow_empty=True
                        ),
                        "condition_evidence": _references(
                            citation["condition_evidence"], allow_empty=True
                        ),
                    }
                )
            except (KeyError, TypeError):
                raise HTTPException(409, "A source reference is unavailable.") from None
        rows.append(
            {
                "id": f"sentence-{index + 1}",
                "index": index,
                "text": original["text"],
                "citations": sources,
            }
        )
    return rows


class VoiceCaseBindingService(ManagedVoiceService):
    def binding_gate(self, owner: uuid.UUID) -> None:
        cfg = self.settings
        if not (
            cfg.voice_case_binding_enabled
            and cfg.voice_tools_enabled
            and cfg.auth_provider == "clerk"
            and cfg.auth_issuer.strip()
            and cfg.environment == "staging"
            and self.test_access(owner)
        ):
            raise HTTPException(503, "Reviewed voice case display is unavailable.")

    async def _context(self, db: AsyncSession, owner: uuid.UUID, voice_id: uuid.UUID) -> None:
        self.binding_gate(owner)
        if not await db.scalar(text("SELECT to_regclass('voice_case_bindings') IS NOT NULL")):
            raise HTTPException(503, "Reviewed voice case storage is unavailable.")
        _, session, call, operation = await self.locked(db, owner, voice_id)
        if (
            session.state not in OPEN_STATES
            or session.expires_at <= await self.now(db)
            or operation.end_requested
            or operation.phase != "connected"
            or call is None
            or call.phase not in ("ready", "active")
            or not call.synthetic
            or not self.settings.voice_development_enabled
            or not self.settings.vaani_byol_enabled
            or not self.settings.vaani_dev_agent_reviewed
        ):
            raise HTTPException(409, "This development voice session cannot display a case.")
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
        processing = await db.scalar(
            select(ConsentRecord)
            .where(
                ConsentRecord.user_id == owner,
                ConsentRecord.scope == "process_comparison",
                ConsentRecord.purpose_version == CONSENT_VERSION,
                ConsentRecord.revoked_at.is_(None),
            )
            .with_for_update(read=True)
        )
        if identity is None or processing is None or not await self.consent(db, owner):
            raise HTTPException(403, "Current identity and case/voice processing consent required.")

    def _advisors(self) -> set[uuid.UUID]:
        try:
            return {uuid.UUID(v) for v in self.settings.advisor_subjects} - {
                uuid.UUID(v) for v in self.settings.auth_test_subjects
            }
        except (ValueError, TypeError):
            raise HTTPException(503, "Advisor authorization is not configured.") from None

    async def _release(
        self, db: AsyncSession, owner: uuid.UUID, row: VoiceCaseBinding
    ) -> dict[str, Any]:
        try:
            result = await report_release.release(
                db,
                self.settings.auth_issuer,
                str(row.case_id),
                owner,
                report_release.ReleaseCommand(
                    request_key=row.release_request_key,
                    turn_id=row.turn_id,
                    report_digest=row.report_digest,
                ),
                self._advisors(),
            )
        except WorkflowError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        receipt = result["release_receipt"]
        if row.release_receipt_id is not None and (
            str(row.release_receipt_id) != receipt["id"]
            or str(row.advisor_event_id) != receipt["advisor_event_id"]
        ):
            raise HTTPException(409, "The original case release decision changed.")
        return result

    @staticmethod
    def _view(row: VoiceCaseBinding) -> dict[str, Any]:
        return {
            "binding_id": str(row.id),
            "voice_session_id": str(row.voice_session_id),
            "case_id": str(row.case_id),
            "turn_id": str(row.turn_id),
            "report_digest": row.report_digest,
            "requested_at": row.created_at.isoformat(),
            "delivery_authorized": False,
        }

    async def bind(
        self,
        owner: uuid.UUID,
        voice_session_id: uuid.UUID,
        case_id: uuid.UUID,
        idempotency_key: uuid.UUID,
    ) -> tuple[dict[str, Any], bool]:
        issuer = self.settings.auth_issuer
        digest = request_digest(
            {
                "operation": "reviewed-case-bind-v1",
                "issuer": issuer,
                "owner": str(owner),
                "voice_session": str(voice_session_id),
                "case_id": str(case_id),
            }
        )
        async with self.factory() as db:
            await self._context(db, owner, voice_session_id)
            await db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"voice-case-bind:{issuer}:{owner}:{idempotency_key}"},
            )
            prior = await db.scalar(
                select(VoiceCaseBinding).where(
                    VoiceCaseBinding.issuer == issuer,
                    VoiceCaseBinding.owner_id == owner,
                    VoiceCaseBinding.request_key == idempotency_key,
                )
            )
            if prior is not None:
                if prior.request_digest != digest:
                    raise HTTPException(409, "The case binding key was used for another request.")
                await self._release(db, owner, prior)
                result = self._view(prior)
                await db.commit()
                return result, False
            if await db.scalar(
                select(VoiceCaseBinding.id).where(
                    VoiceCaseBinding.voice_session_id == voice_session_id,
                )
            ):
                raise HTTPException(
                    409, "This voice session already has an immutable case binding."
                )
            # Determine a stable release key BEFORE acquiring report head (same order as release).
            release_key = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"assurely:voice-case-release:{issuer}:{owner}:{voice_session_id}",
            )
            await db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"release:{issuer}:{owner}:{release_key}"},
            )
            try:
                current = await report_release.head(db, issuer, str(case_id), owner)
            except WorkflowError as exc:
                raise HTTPException(exc.status, str(exc)) from exc
            if not current.report_digest:
                raise HTTPException(409, "The current reviewed report is unavailable.")
            row = VoiceCaseBinding(
                id=uuid.uuid4(),
                voice_session_id=voice_session_id,
                issuer=issuer,
                owner_id=owner,
                case_id=case_id,
                turn_id=current.turn_id,
                report_digest=current.report_digest,
                request_key=idempotency_key,
                request_digest=digest,
                release_request_key=release_key,
            )
            released = await self._release(db, owner, row)
            # Validate source projection before committing either receipt or binding.
            reviewed_caption_packet(released["output"])
            row.release_receipt_id = uuid.UUID(released["release_receipt"]["id"])
            row.advisor_event_id = uuid.UUID(released["release_receipt"]["advisor_event_id"])
            db.add(row)
            await db.flush()
            result = self._view(row)
            await db.commit()
            return result, True

    async def _read(
        self, owner: uuid.UUID, voice_session_id: uuid.UUID, *, captions: bool
    ) -> dict[str, Any]:
        async with self.factory() as db:
            await self._context(db, owner, voice_session_id)
            row = await db.scalar(
                select(VoiceCaseBinding).where(
                    VoiceCaseBinding.voice_session_id == voice_session_id,
                    VoiceCaseBinding.issuer == self.settings.auth_issuer,
                    VoiceCaseBinding.owner_id == owner,
                )
            )
            if row is None:
                raise HTTPException(404, "Voice case binding not found.")
            released = await self._release(db, owner, row)
            result = self._view(row)
            if captions:
                sentences = reviewed_caption_packet(released["output"])
                event = await db.get(AdvisorDecision, row.advisor_event_id)
                assert event is not None and event.expires_at is not None
                expiry = min(
                    event.expires_at,
                    *(
                        datetime.fromisoformat(c["expires_at"])
                        for s in sentences
                        for c in s["citations"]
                    ),
                )
                from app.models.db.voice import VoiceSession

                session = await db.get(VoiceSession, voice_session_id)
                assert session is not None
                # Browser displays expire promptly even when a request/hold changes later.
                # This is a short presentation lease, not future release authority.
                expiry = min(expiry, session.expires_at, await self.now(db) + timedelta(seconds=10))
                if expiry <= datetime.now(UTC):
                    raise HTTPException(409, "The case display authorization expired.")
                result.update(
                    {
                        "sentences": copy.deepcopy(sentences),
                        "expires_at": expiry.isoformat(),
                        "safe_for_display": True,
                        "caption_scope": "authorized_report_excerpt",
                        "realtime_transcript": False,
                        "external_speech_enabled": False,
                    }
                )
            await db.commit()
            return result

    async def read_binding(self, owner: uuid.UUID, voice_session_id: uuid.UUID) -> dict[str, Any]:
        return await self._read(owner, voice_session_id, captions=False)

    async def captions(self, owner: uuid.UUID, voice_session_id: uuid.UUID) -> dict[str, Any]:
        return await self._read(owner, voice_session_id, captions=True)
