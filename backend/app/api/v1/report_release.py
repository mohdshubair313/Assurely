"""Owner-only current-report metadata and transactional release endpoint."""

import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.v1.policy_reviews import _body
from app.core.config import get_settings
from app.core.security import require_authenticated_user_id
from app.db import report_release as store
from app.db.policy_review_store import WorkflowError
from app.db.session import AsyncSessionLocal

router = APIRouter(prefix="/sessions")
Owner = Annotated[uuid.UUID, Depends(require_authenticated_user_id)]


@router.get("/{session_id}/report-status")
async def status(session_id: str, owner: Owner) -> dict[str, Any]:
    try:
        async with AsyncSessionLocal() as db, db.begin():
            row = await store.head(db, get_settings().auth_issuer, session_id, owner)
            result = {
                "turn_id": str(row.turn_id),
                "report_digest": row.report_digest,
                "status": row.status,
                "delivery_hold": True,
            }
        return result
    except WorkflowError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


@router.post("/{session_id}/report-release")
async def release(session_id: str, request: Request, owner: Owner) -> dict[str, Any]:
    try:
        command = store.ReleaseCommand.model_validate_json(json.dumps(await _body(request, 16_384)))
    except ValueError as exc:
        raise HTTPException(422, "Invalid report release request.") from exc
    settings = get_settings()
    if settings.environment == "development":
        raise HTTPException(409, "Reviewed report release is disabled in development mode.")
    try:
        advisors = {uuid.UUID(value) for value in settings.advisor_subjects}
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(503, "Advisor authorization is not configured.") from exc
    try:
        async with AsyncSessionLocal() as db, db.begin():
            result = await store.release(
                db, settings.auth_issuer, session_id, owner, command, advisors
            )
        # Commit (including receipt) completed before the response can expose output.
        return result
    except WorkflowError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
