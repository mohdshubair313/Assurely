"""Reuse the current report's release gate; never generate a second insurance answer.

V3 tools are deliberately independent of the synthetic-media agent. Speech/captions/
recaps may use only this exact packet, with a fresh authorization read at delivery.
"""

import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.graph.nodes.guardrail import check_ranking_language, check_unlicensed_advice


def speech_packet(output: dict[str, Any]) -> dict[str, Any]:
    if output.get("report_status") != "ready":
        raise HTTPException(409, "The report is awaiting validation.")
    sentences = output.get("sentences")
    if not isinstance(sentences, list) or not 1 <= len(sentences) <= 32:
        raise HTTPException(409, "Sourced report sentences are unavailable.")
    normalized: list[dict[str, Any]] = []
    for item in sentences:
        if not isinstance(item, dict):
            raise HTTPException(409, "Report evidence is unavailable.")
        text = item.get("text")
        citations = item.get("citations")
        if (
            not isinstance(text, str)
            or not text.strip()
            or len(text) > 4096
            or check_ranking_language(text)
            or check_unlicensed_advice(text)
            or not isinstance(citations, list)
            or not citations
        ):
            raise HTTPException(409, "A report sentence cannot be released.")
        safe = []
        for source in citations:
            try:
                if (
                    not isinstance(source, dict)
                    or not isinstance(source.get("source"), str)
                    or not source["source"].strip()
                ):
                    raise ValueError()
                verified = source["last_verified"]
                if not isinstance(verified, str):
                    raise ValueError()
                if len(verified) != 10:
                    verified_at = datetime.fromisoformat(verified)
                    if verified_at.tzinfo is None:
                        raise ValueError()
                stamp = date.fromisoformat(verified[:10])
                if stamp > datetime.now(UTC).date():
                    raise ValueError()
                if source.get("expires_at") and datetime.fromisoformat(
                    source["expires_at"]
                ) <= datetime.now(UTC):
                    raise ValueError()
                safe.append({"source": source["source"], "last_verified": verified})
            except (KeyError, ValueError, TypeError):
                raise HTTPException(409, "A source is missing current verification.") from None
        # Preserve the full original sentence and its conditions; no paraphrase or new figures.
        normalized.append({"text": text, "citations": safe})
    digest = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "sentences": normalized,
        "speech": " ".join(item["text"] for item in normalized),
        "report_digest": digest,
        "generated_by": "existing_explanation_report",
        "new_calculation": False,
        "human_approval_granted": False,
    }


async def current_packet(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    owner: uuid.UUID,
    case_id: uuid.UUID,
) -> dict[str, Any]:
    from sqlalchemy import select

    from app.api.v1.message import build_delivery_response, get_app_graph
    from app.core.consent import CONSENT_VERSION
    from app.graph.runtime import read_config
    from app.models.db.consent_record import ConsentRecord
    from app.models.db.session import Session

    if not settings.voice_tools_enabled:
        raise HTTPException(503, "Voice evidence tools are not enabled.")
    async with factory() as db:
        case = await db.get(Session, case_id)
        if not case or case.user_id != owner:
            raise HTTPException(404, "Case not found.")
        if not await db.scalar(
            select(ConsentRecord.id).where(
                ConsentRecord.user_id == owner,
                ConsentRecord.scope == "process_comparison",
                ConsentRecord.purpose_version == CONSENT_VERSION,
                ConsentRecord.revoked_at.is_(None),
            )
        ):
            raise HTTPException(403, "Current insurance processing consent is required.")
    config = await read_config(str(case_id), current_only=True)
    checkpoint = await get_app_graph().aget_state(config) if config is not None else None
    if not checkpoint or checkpoint.values.get("user_id") != str(owner):
        raise HTTPException(404, "Current case report is unavailable.")
    response = await build_delivery_response(str(case_id), checkpoint.values)
    if response.delivery_hold or not response.approved:
        raise HTTPException(409, "The report remains held for validation or human review.")
    return {"case_id": str(case_id), **speech_packet(response.output)}


async def case_turn(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    owner: uuid.UUID,
    case_id: uuid.UUID,
    text: str,
    request: Request,
) -> dict[str, Any]:
    """Run follow-up text through the existing pipeline, never through a second voice LLM.

    This server-only bridge is not wired to the synthetic Vaani agent. Real voice
    case binding and privacy acceptance must precede external insurance conversations.
    """
    from sqlalchemy import select

    from app.api.v1.message import MessageRequest, send_message
    from app.core.consent import CONSENT_VERSION
    from app.models.db.consent_record import ConsentRecord
    from app.models.db.session import Session

    if not settings.voice_tools_enabled:
        raise HTTPException(503, "Voice case tools are unavailable.")
    async with factory() as db:
        case = await db.get(Session, case_id)
        if not case or case.user_id != owner:
            raise HTTPException(404, "Case not found.")
        if not await db.scalar(
            select(ConsentRecord.id).where(
                ConsentRecord.user_id == owner,
                ConsentRecord.scope == "process_comparison",
                ConsentRecord.purpose_version == CONSENT_VERSION,
                ConsentRecord.revoked_at.is_(None),
            )
        ):
            raise HTTPException(403, "Current insurance processing consent is required.")
    response = await send_message(
        MessageRequest(session_id=str(case_id), user_message=text), request, owner
    )
    if response.delivery_hold:
        return {
            "case_id": str(case_id),
            "delivery_hold": True,
            "sentences": [],
            "speech": (
                "The response remains held for validation or human review. "
                "Please continue in your case workspace."
            ),
            "human_approval_granted": False,
        }
    packet = await current_packet(factory, settings, owner, case_id)
    return {"delivery_hold": False, **packet}
