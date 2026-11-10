"""Owner-scoped synthetic demo APIs; no audio or live provider calls."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict

from app.core.config import get_settings
from app.core.security import require_authenticated_user_id
from app.db.session import AsyncSessionLocal
from app.models.db.voice import VoiceSession
from app.voice.service import VoiceSessionService

router = APIRouter(prefix="/voice")
Owner = Annotated[uuid.UUID, Depends(require_authenticated_user_id)]


class VoiceStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: Literal["en", "hi", "hinglish"] = "en"
    idempotency_key: uuid.UUID


class VoiceTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: Literal["copay", "estimate", "agent_claim", "human_review"]


class VoiceEndRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: uuid.UUID | None = None


def service() -> VoiceSessionService:
    return VoiceSessionService(AsyncSessionLocal, get_settings())


@router.get("/entitlement")
async def get_voice_entitlement(user_id: Owner) -> dict[str, object]:
    return await service().entitlement(user_id)


@router.post("/sessions", status_code=201)
async def start_voice_session(
    body: VoiceStartRequest, user_id: Owner, response: Response
) -> dict[str, object]:
    session, created = await service().start(user_id, body.language, body.idempotency_key)
    response.status_code = 201 if created else 200
    return _session_payload(session)


@router.get("/sessions/{session_id}")
async def get_voice_session(session_id: uuid.UUID, user_id: Owner) -> dict[str, object]:
    session = await service().read(user_id, session_id)
    assert session is not None
    return _session_payload(session)


@router.get("/active")
async def get_active_voice_session(user_id: Owner) -> dict[str, object]:
    session = await service().read(user_id)
    return {"session": _session_payload(session) if session else None}


@router.post("/sessions/{session_id}/turn")
async def demo_voice_turn(
    session_id: uuid.UUID, body: VoiceTurnRequest, user_id: Owner
) -> dict[str, object]:
    session = await service().read(user_id, session_id, turn=True)
    assert session is not None
    answers = {
        "copay": (
            "AI guide: In this synthetic demo, the fixture lists co-payment as 10%. "
            "This is not a real policy term."
        ),
        "estimate": (
            "AI guide: For the synthetic fixture, a \u20b95,00,000 admissible amount with a 10% "
            "co-payment gives a \u20b950,000 member share under the demo assumption. "
            "This is arithmetic for a fictional fixture, not a claim payout estimate."
        ),
        "agent_claim": (
            "AI guide: I cannot verify a sales statement without a real policy source. "
            "Please use the evidence review flow for an actual document."
        ),
        "human_review": (
            "AI guide: This local prototype cannot create or decide a human review. "
            "Use the existing signed-in case review path; any delivery hold remains in force."
        ),
    }
    return {
        "session_id": str(session_id),
        "answer": answers[body.prompt],
        "evidence": [
            {
                "source_title": "Synthetic demo policy fixture",
                "version": "demo-1",
                "last_verified": "2026-11-05",
                "verified": False,
                "synthetic": True,
            }
        ],
        "audio_connected": False,
        "transcript_persisted": False,
    }


@router.post("/sessions/{session_id}/end")
async def end_voice_session(
    session_id: uuid.UUID, body: VoiceEndRequest, user_id: Owner
) -> dict[str, object]:
    return _session_payload(await service().end(user_id, session_id, body.idempotency_key))


def _session_payload(session: VoiceSession) -> dict[str, object]:
    now = datetime.now(UTC)
    elapsed = min(now, session.ended_at or now, session.expires_at) - session.created_at
    return {
        "session_id": str(session.id),
        "state": session.state,
        "provider": session.provider,
        "language": session.language,
        "reserved_seconds": session.reserved_seconds,
        "consumed_seconds": session.consumed_seconds,
        "elapsed_seconds": max(0, int(elapsed.total_seconds())),
        "expires_at": session.expires_at.isoformat(),
        "audio_connected": False,
        "transcript_persisted": False,
        "ai_disclosure": (
            "I am an AI insurance guide. This no-audio prototype uses a fictional policy fixture."
        ),
    }
