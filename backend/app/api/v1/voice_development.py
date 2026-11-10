"""Clerk-owned synthetic audio control API. No customer calls or billing activation."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.core.security import require_authenticated_user_id
from app.db.session import AsyncSessionLocal
from app.voice.managed import ManagedVoiceService

router = APIRouter(prefix="/voice/development")
Owner = Annotated[uuid.UUID, Depends(require_authenticated_user_id)]


class Start(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: uuid.UUID


class RecapRequest(Start):
    case_id: uuid.UUID


class CaseTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=4000)


def service() -> ManagedVoiceService:
    return ManagedVoiceService(AsyncSessionLocal, get_settings())


@router.post("/sessions/{session_id}/case-binding")
async def bind_case(
    session_id: uuid.UUID, request: Request, owner: Owner, response: Response
) -> dict[str, Any]:
    import json

    from fastapi import HTTPException

    from app.api.v1.policy_reviews import _body
    from app.voice.case_binding import BindCaseCommand, VoiceCaseBindingService

    try:
        body = BindCaseCommand.model_validate_json(json.dumps(await _body(request, 4096)))
    except ValueError:
        raise HTTPException(422, "Invalid case binding request.") from None
    result, created = await VoiceCaseBindingService(AsyncSessionLocal, get_settings()).bind(
        owner, session_id, body.case_id, body.idempotency_key
    )
    response.status_code = 201 if created else 200
    return result


@router.get("/sessions/{session_id}/case-binding")
async def read_case_binding(session_id: uuid.UUID, owner: Owner) -> dict[str, Any]:
    from app.voice.case_binding import VoiceCaseBindingService

    return await VoiceCaseBindingService(AsyncSessionLocal, get_settings()).read_binding(
        owner, session_id
    )


@router.get("/sessions/{session_id}/captions")
async def case_captions(session_id: uuid.UUID, owner: Owner) -> dict[str, Any]:
    from app.voice.case_binding import VoiceCaseBindingService

    return await VoiceCaseBindingService(AsyncSessionLocal, get_settings()).captions(
        owner, session_id
    )


@router.post("/recaps")
async def create_recap(body: RecapRequest, owner: Owner) -> dict[str, Any]:
    from app.voice.recaps import RecapService

    return await RecapService(AsyncSessionLocal, get_settings()).create_recap(
        owner, body.case_id, body.idempotency_key
    )


@router.get("/recaps/{recap_id}")
async def read_recap(recap_id: uuid.UUID, owner: Owner) -> dict[str, Any]:
    from app.voice.recaps import RecapService

    return await RecapService(AsyncSessionLocal, get_settings()).read_recap(owner, recap_id)


@router.delete("/recaps/{recap_id}")
async def delete_recap(recap_id: uuid.UUID, owner: Owner) -> dict[str, Any]:
    from app.voice.recaps import RecapService

    return await RecapService(AsyncSessionLocal, get_settings()).delete_recap(owner, recap_id)


@router.get("/availability")
async def availability(owner: Owner) -> dict[str, Any]:
    try:
        service().gate(owner)
        return {"enabled": True, "synthetic": True, "billing_enabled": False}
    except Exception:
        return {"enabled": False, "synthetic": True, "billing_enabled": False}


@router.get("/cases/{case_id}/evidence")
async def evidence(case_id: uuid.UUID, owner: Owner) -> dict[str, Any]:
    from app.voice.evidence import current_packet

    return await current_packet(AsyncSessionLocal, get_settings(), owner, case_id)


@router.post("/cases/{case_id}/turn")
async def case_turn(
    case_id: uuid.UUID, body: CaseTurn, request: Request, owner: Owner
) -> dict[str, Any]:
    from app.voice.evidence import case_turn

    return await case_turn(AsyncSessionLocal, get_settings(), owner, case_id, body.text, request)


@router.get("/release-status")
async def release_status(owner: Owner) -> dict[str, Any]:
    from app.voice.release import release_status

    return release_status(get_settings())


@router.post("/billing/checkout")
async def checkout(body: Start, owner: Owner) -> dict[str, Any]:
    from app.voice.billing import TestBillingService

    return await TestBillingService(AsyncSessionLocal, get_settings()).checkout(
        owner, body.idempotency_key
    )


@router.post("/sessions")
async def start(body: Start, owner: Owner, response: Response) -> dict[str, Any]:
    svc = service()
    session, created = await svc.reserve(owner, body.idempotency_key)
    response.status_code = 201 if created else 200
    # Create is durable and dispatched once; bind its room BEFORE the connect POST starts audio.
    await svc.advance(owner, session.id)
    await svc.advance(owner, session.id)
    return await svc.view(owner, session.id)


@router.get("/sessions/{session_id}")
async def status(session_id: uuid.UUID, owner: Owner) -> dict[str, Any]:
    return await service().view(owner, session_id)


@router.post("/sessions/{session_id}/connect")
async def connect(session_id: uuid.UUID, owner: Owner) -> dict[str, Any]:
    svc = service()
    svc.gate(owner)
    await svc.advance(owner, session_id, connect=True)
    return await svc.view(owner, session_id, material=True)


@router.get("/sessions/{session_id}/authorization")
async def authorization(session_id: uuid.UUID, owner: Owner) -> dict[str, Any]:
    return await service().view(owner, session_id)


@router.post("/sessions/{session_id}/end")
async def end(session_id: uuid.UUID, owner: Owner) -> dict[str, Any]:
    svc = service()
    result = await svc.request_end(owner, session_id)
    # Worker performs hard-end outside request locks and continues after client disconnect/restart.
    return result
