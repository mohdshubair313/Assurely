"""Concurrent receive and one-shot complete responses; no streaming unchecked text.

A newer documented response_id cancels unsent work. Bytes already handed to the
provider cannot be recalled here; real TTS cancellation remains an external gate.
All database decisions commit before bounded socket I/O. Disconnect never settles
voice usage or proves provider termination.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections import deque
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any, NoReturn

from fastapi import WebSocket

from app.voice.byol import BindingDeniedError, ByolTurn
from app.voice.byol_evidence import VoiceByolEvidenceService, turn_digest

DB_TIMEOUT = 3.0
SEND_TIMEOUT = 1.0
CANCEL_TIMEOUT = 0.3
MAX_FRAMES_PER_MINUTE = 120
MAX_TURNS_PER_MINUTE = 30


def parse_frame(raw: str) -> Any:
    """Bound the UTF-8 body and reject duplicate members before interpreting it."""
    if len(raw.encode("utf-8")) > 32768:
        raise ValueError("Provider frame exceeds the permitted size.")

    def unique(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate provider frame member.")
            result[key] = value
        return result

    def invalid_constant(value: str) -> NoReturn:
        raise ValueError("Non-finite provider JSON number.")

    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)


async def _cancel(task: asyncio.Task[None] | None) -> None:
    if task is None:
        return
    task.cancel()
    done, pending = await asyncio.wait({task}, timeout=CANCEL_TIMEOUT)
    for result in done:
        with suppress(Exception, asyncio.CancelledError):
            result.result()
    if pending:
        # An uncooperative operation cannot be allowed to emit an obsolete answer.
        # The local generation fence also remains invalid after this error.
        raise RuntimeError("Provider operation cancellation is pending.")


async def run_evidence_dialogue(
    websocket: WebSocket,
    service: VoiceByolEvidenceService,
    room: str,
    connection_id: uuid.UUID,
    heartbeat: Callable[[], Awaitable[None]],
) -> None:
    """Already-authenticated socket; caller owns connection lease release/close."""
    generation = 0
    highest_id = 0
    fingerprints: dict[int, str] = {}
    frames: deque[float] = deque()
    turns: deque[float] = deque()
    active: asyncio.Task[None] | None = None
    receiver: asyncio.Task[str] | None = None
    send_lock = asyncio.Lock()

    async def respond(turn: ByolTurn, expected: int) -> None:
        ticket = await asyncio.wait_for(
            service.begin(room, connection_id, turn), timeout=DB_TIMEOUT
        )
        if ticket is None or expected != generation:
            return
        prepared = await asyncio.wait_for(service.prepare(ticket, turn), timeout=DB_TIMEOUT)
        if expected != generation:
            return
        async with send_lock:
            if expected != generation:
                return
            authorized = await asyncio.wait_for(
                service.authorize_send(prepared), timeout=DB_TIMEOUT
            )
            # The service committed a non-replayable send_unknown intent. This
            # immediate check is a bounded permission window, not a future grant.
            if expected != generation or authorized.expires_at <= datetime.now(UTC):
                return
            await asyncio.wait_for(websocket.send_json(authorized.frame), timeout=SEND_TIMEOUT)
        if expected == generation:
            await asyncio.wait_for(service.complete(ticket), timeout=DB_TIMEOUT)

    try:
        while True:
            if receiver is None:
                receiver = asyncio.create_task(websocket.receive_text())
            pending: set[asyncio.Task[Any]] = {receiver}
            if active is not None:
                pending.add(active)
            done, _ = await asyncio.wait(pending, timeout=5, return_when=asyncio.FIRST_COMPLETED)
            if not done:
                await asyncio.wait_for(heartbeat(), timeout=DB_TIMEOUT)
                async with send_lock:
                    await asyncio.wait_for(
                        websocket.send_json({"response_type": "ping_pong"}),
                        timeout=SEND_TIMEOUT,
                    )
                continue
            # Prioritize a received newer request over unsent local work. A
            # response already sent before this event remains provider-owned.
            if receiver in done:
                raw = receiver.result()
                receiver = None
                body = parse_frame(raw)
                now = asyncio.get_running_loop().time()
                for timestamps in (frames, turns):
                    while timestamps and timestamps[0] <= now - 60:
                        timestamps.popleft()
                frames.append(now)
                if len(frames) > MAX_FRAMES_PER_MINUTE:
                    raise BindingDeniedError()
                if body == {"response_type": "ping_pong"}:
                    await asyncio.wait_for(heartbeat(), timeout=DB_TIMEOUT)
                    continue
                turn = ByolTurn.model_validate(body)
                if turn.interaction_type != "response_required" or turn.call_id != room:
                    raise BindingDeniedError()
                fingerprint = turn_digest(turn)
                if turn.response_id <= highest_id:
                    if (
                        turn.response_id in fingerprints
                        and fingerprints[turn.response_id] != fingerprint
                    ):
                        raise BindingDeniedError()
                    await asyncio.wait_for(heartbeat(), timeout=DB_TIMEOUT)
                    continue
                turns.append(now)
                if len(turns) > MAX_TURNS_PER_MINUTE:
                    raise BindingDeniedError()
                highest_id = turn.response_id
                fingerprints[turn.response_id] = fingerprint
                if len(fingerprints) > 32:
                    del fingerprints[min(fingerprints)]
                # Fence synchronously before any heartbeat/DB await: otherwise
                # already-buffered old work could emit while renewal is pending.
                generation += 1
                await _cancel(active)
                active = None
                await asyncio.wait_for(heartbeat(), timeout=DB_TIMEOUT)
                active = asyncio.create_task(respond(turn, generation))
                continue
            if active is not None and active in done:
                active.result()  # Authentication/storage failures close safely in the caller.
                active = None
    finally:
        generation += 1
        if receiver is not None:
            receiver.cancel()
        try:
            await _cancel(active)
        finally:
            if receiver is not None:
                done, _ = await asyncio.wait({receiver}, timeout=CANCEL_TIMEOUT)
                for result in done:
                    with suppress(Exception, asyncio.CancelledError):
                        result.result()
