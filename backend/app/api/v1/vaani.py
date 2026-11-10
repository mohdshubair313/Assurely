"""Provider-owned ingress is authenticated separately from the Clerk browser gateway."""

import asyncio
import hmac
import json
import re
import uuid

import anyio
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.voice.byol import (
    SAFE_RESPONSE,
    BindingDeniedError,
    ByolTurn,
    authorize_connection,
    release_connection,
)
from app.voice.events import MAX_BODY, receive_event
from app.voice.vaani import valid_room

router = APIRouter()
BODY_RECEIVE_TIMEOUT = 5


@router.post("/webhooks/razorpay-test")
async def billing_webhook(request: Request) -> dict[str, object]:
    from app.voice.billing import TestBillingService, test_gate

    settings = get_settings()
    test_gate(settings)
    signatures = request.headers.getlist("x-razorpay-signature")
    event_ids = request.headers.getlist("x-razorpay-event-id")
    if len(signatures) != 1 or len(event_ids) != 1:
        raise HTTPException(401, "Billing signature and event identifier required.")
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(415, "A JSON event is required.")
    raw = bytearray()
    try:
        async with asyncio.timeout(BODY_RECEIVE_TIMEOUT):
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > 65536:
                    raise HTTPException(413, "Billing event exceeds the permitted size.")
    except TimeoutError:
        raise HTTPException(408, "Billing event body did not arrive in time.") from None
    return await TestBillingService(AsyncSessionLocal, settings).receive(
        bytes(raw), signatures[0], event_ids[0]
    )


@router.post("/webhooks/vaani")
async def vaani_webhook(request: Request) -> dict[str, object]:
    settings = get_settings()
    if not settings.vaani_ingress_enabled:
        raise HTTPException(503, "Provider event ingress is disabled.")
    signatures = request.headers.getlist("x-webhook-signature")
    if len(signatures) != 1:
        raise HTTPException(401, "Provider event signature is required.")
    if not re.fullmatch(r"(?:sha256=)?[a-fA-F0-9]{64}", signatures[0]):
        raise HTTPException(401, "Provider event signature is invalid.")
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(415, "A JSON provider event is required.")
    lengths = request.headers.getlist("content-length")
    if lengths and (len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,9}", lengths[0])):
        raise HTTPException(400, "Provider event length is invalid.")
    if lengths and int(lengths[0]) > MAX_BODY:
        raise HTTPException(413, "Provider event exceeds the permitted size.")
    raw = bytearray()
    try:
        async with asyncio.timeout(BODY_RECEIVE_TIMEOUT):
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > MAX_BODY:
                    raise HTTPException(413, "Provider event exceeds the permitted size.")
    except TimeoutError:
        raise HTTPException(408, "Provider event body did not arrive in time.") from None
    if lengths and len(raw) != int(lengths[0]):
        raise HTTPException(400, "Provider event length is invalid.")
    try:
        duplicate = await asyncio.wait_for(
            receive_event(AsyncSessionLocal, settings, bytes(raw), signatures[0]), timeout=3
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Provider event could not be durably recorded.") from None
    return {"status": "received", "duplicate": duplicate}


@router.websocket("/voice/provider/byol/{provider_call_id}")
async def byol_socket(websocket: WebSocket, provider_call_id: str) -> None:
    settings = get_settings()
    token = settings.vaani_byol_token.get_secret_value()
    supplied = websocket.headers.getlist("authorization")
    if (
        not settings.vaani_byol_enabled
        or not settings.vaani_dev_agent_reviewed
        or len(token) < 32
        or len(supplied) != 1
        or not valid_room(provider_call_id)
        or not hmac.compare_digest(supplied[0].encode(), ("Bearer " + token).encode())
    ):
        await websocket.close(code=1008)
        return
    connection_id = uuid.uuid4()
    claimed = False
    accepted = False

    async def free_lease() -> None:
        nonlocal claimed
        if claimed:
            # ASGI disconnect cancellation must not strand a lease after a clean close.
            with anyio.CancelScope(shield=True):
                try:
                    await asyncio.wait_for(
                        release_connection(
                            AsyncSessionLocal, settings, provider_call_id, connection_id
                        ),
                        timeout=3,
                    )
                    claimed = False
                except Exception:
                    pass  # Bounded persisted lease is the crash/outage recovery fallback.

    try:
        await authorize_connection(AsyncSessionLocal, settings, provider_call_id, connection_id)
        claimed = True
        await websocket.accept()
        accepted = True
        await websocket.send_json({"interaction_type": "config", "content": "Server ready"})
        await websocket.send_json({"interaction_type": "greeting", "content": "Synthetic session"})
        if settings.voice_byol_evidence_enabled:
            from app.voice.byol_evidence import VoiceByolEvidenceService
            from app.voice.byol_runtime import run_evidence_dialogue

            async def heartbeat() -> None:
                await authorize_connection(
                    AsyncSessionLocal, settings, provider_call_id, connection_id
                )

            await run_evidence_dialogue(
                websocket,
                VoiceByolEvidenceService(AsyncSessionLocal, settings),
                provider_call_id,
                connection_id,
                heartbeat,
            )
            return
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=5)
            except TimeoutError:
                await authorize_connection(
                    AsyncSessionLocal, settings, provider_call_id, connection_id
                )
                await websocket.send_json({"response_type": "ping_pong"})
                continue
            if len(message.encode()) > 32768:
                await free_lease()
                await websocket.close(code=1009)
                return
            body = json.loads(message)
            if body == {"response_type": "ping_pong"}:
                await authorize_connection(
                    AsyncSessionLocal, settings, provider_call_id, connection_id
                )
                continue
            turn = ByolTurn.model_validate(body)
            if turn.interaction_type != "response_required" or turn.call_id != provider_call_id:
                raise BindingDeniedError()
            await authorize_connection(
                AsyncSessionLocal, settings, provider_call_id, connection_id, turn.response_id
            )
            # Deliberately ignore untrusted system messages, utterances and runtime overrides.
            # No model or case tools run in V2a. Nothing from the transcript is retained or echoed.
            await websocket.send_json(
                {
                    "response_type": "response",
                    "response_id": turn.response_id,
                    "content": SAFE_RESPONSE,
                    "content_complete": True,
                }
            )
    except WebSocketDisconnect:
        pass
    except HTTPException as exc:
        await free_lease()
        await websocket.close(code=1008 if exc.status_code < 500 else 1011)
    except (BindingDeniedError, ValidationError, ValueError, TypeError, RecursionError):
        await free_lease()
        await websocket.close(code=1008)
    except Exception:
        # A protocol/DB outage never falls through to a platform LLM or raw error response.
        await free_lease()
        await websocket.close(code=1011 if accepted else 1008)
    finally:
        await free_lease()
