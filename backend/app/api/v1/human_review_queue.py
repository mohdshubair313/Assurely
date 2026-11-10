"""Private admin intake for persisted customer requests, with no delivery authority."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.policy_reviews import Database
from app.core.security import (
    AuthenticatedPrincipal,
    is_test_account,
    require_admin,
    server_roles,
)
from app.db.human_review_queue import read_queue
from app.db.policy_review_store import WorkflowError

router = APIRouter()


def require_queue_admin(
    principal: Annotated[AuthenticatedPrincipal, Depends(require_admin)],
) -> AuthenticatedPrincipal:
    if principal.provider != "clerk" or not principal.issuer.strip():
        raise HTTPException(503, "Clerk operator authentication is required.")
    if is_test_account(principal.user_id) or "admin" not in server_roles(principal.user_id):
        raise HTTPException(403, "Administrator authorization is required.")
    return principal


class QueueItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    escalation_id: uuid.UUID
    session_id: uuid.UUID
    request_id: uuid.UUID
    requested_at: datetime
    status: Literal["pending", "assigned", "in_review"]


class QueuePage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[QueueItem] = Field(max_length=100)
    truncated: bool
    pagination: Literal["first_page_only"]
    notification_confirmed: Literal[False]
    delivery_authorized: Literal[False]


@router.get("/admin/human-review-queue", response_model=QueuePage)
async def human_review_queue(
    admin: Annotated[AuthenticatedPrincipal, Depends(require_queue_admin)],
    db: Database,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> dict[str, Any]:
    """Read only; assignment remains the separate audited administrator workflow."""
    try:
        return await read_queue(db, admin.issuer, limit)
    except WorkflowError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
