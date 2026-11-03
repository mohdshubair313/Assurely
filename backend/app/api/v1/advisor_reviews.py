"""Authenticated advisor snapshot/review workflow; no customer release endpoint."""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.v1.policy_reviews import Database, Digest, _body
from app.core.advisor_auth import require_advisor
from app.db import advisor_review as store
from app.db.policy_review_store import Reviewer, WorkflowError

router = APIRouter(prefix="/advisor-reviews")
Advisor = Annotated[Reviewer, Depends(require_advisor)]


@router.post("/sessions/{session_id}/snapshot")
async def snapshot(session_id: str, actor: Advisor, db: Database) -> dict[str, Any]:
    from app.api.v1.message import _app_graph

    checkpoint = await _app_graph.aget_state({"configurable": {"thread_id": session_id}})
    if not checkpoint or not checkpoint.values:
        raise HTTPException(404, "Current report checkpoint is unavailable.")
    try:
        return await store.stage(db, actor, session_id, checkpoint.values)
    except WorkflowError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(409, "Report evidence cannot be staged.") from exc


@router.get("/{digest}")
async def read(digest: Digest, actor: Advisor, db: Database) -> dict[str, Any]:
    try:
        return await store.read(db, actor, digest)
    except WorkflowError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


@router.post("/{digest}/decisions")
async def decide(digest: Digest, request: Request, actor: Advisor, db: Database) -> dict[str, Any]:
    try:
        command = store.DecisionCommand.model_validate_json(
            json.dumps(await _body(request, 16_384))
        )
        return await store.decide(db, actor, digest, command)
    except WorkflowError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, "Invalid advisor decision.") from exc
