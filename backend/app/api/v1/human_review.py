"""Clerk-owned customer review requests; no voice subscription is required."""

import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.v1.policy_reviews import _body
from app.core.config import get_settings
from app.core.security import require_authenticated_user_id
from app.db import human_review as store
from app.db.policy_review_store import WorkflowError
from app.db.session import AsyncSessionLocal

router = APIRouter(prefix="/sessions")
Owner = Annotated[uuid.UUID, Depends(require_authenticated_user_id)]


def _issuer() -> str:
    settings = get_settings()
    if settings.auth_provider != "clerk" or not settings.auth_issuer.strip():
        raise HTTPException(503, "Human review identity is not configured.")
    return settings.auth_issuer


@router.get("/{session_id}/human-review")
async def read(session_id: uuid.UUID, owner: Owner) -> dict[str, Any]:
    issuer = _issuer()
    try:
        async with AsyncSessionLocal() as db, db.begin():
            return await store.read(db, issuer, session_id, owner)
    except WorkflowError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


@router.post("/{session_id}/human-review")
async def create(session_id: uuid.UUID, request: Request, owner: Owner) -> dict[str, Any]:
    issuer = _issuer()
    try:
        command = store.RequestCommand.model_validate_json(json.dumps(await _body(request, 4096)))
    except ValueError as exc:
        raise HTTPException(422, "Invalid human review request.") from exc
    try:
        async with AsyncSessionLocal() as db, db.begin():
            result = await store.create(db, issuer, session_id, owner, command)
        return result  # Receipt commit completes before acknowledging the request.
    except WorkflowError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
