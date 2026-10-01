"""GET /v1/session/{id} — retrieve session details.

Powers the "why am I seeing this" explainability view and the audit trail.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.correlation import SESSION_NAMESPACE, database_session_id
from app.core.security import optional_authenticated_user_id
from app.db.session import AsyncSessionLocal
from app.models.db.session import Session as DBSession

router = APIRouter()


class SessionDetailResponse(BaseModel):
    session_id: str
    status: str
    intent: str | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    calculator_outputs: dict[str, Any] = Field(default_factory=dict)


@router.get("/session/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: str,
    authenticated_user_id: Annotated[
        uuid.UUID | None, Depends(optional_authenticated_user_id)
    ] = None,
) -> SessionDetailResponse:
    """Retrieve session audit state with ownership verification."""
    from app.api.v1.message import _app_graph, build_message_response

    db_session_id = database_session_id(session_id)
    checkpoint = await _app_graph.aget_state({"configurable": {"thread_id": session_id}})
    has_checkpoint = bool(
        checkpoint and checkpoint.values and checkpoint.values.get("messages")
    )

    async with AsyncSessionLocal() as db:
        db_session = await db.get(DBSession, db_session_id)

    if not has_checkpoint and db_session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    # Determine ownership
    owner_user_id: str | None = None
    if has_checkpoint:
        owner_user_id = checkpoint.values.get("user_id")
    if owner_user_id is None and db_session is not None:
        anon_user_id = uuid.uuid5(SESSION_NAMESPACE, f"user:{db_session_id}")
        if db_session.user_id != anon_user_id:
            owner_user_id = str(db_session.user_id)

    # Enforce ownership rules
    if owner_user_id is not None:
        # Authenticated session: requires matching verified token
        if authenticated_user_id is None:
            raise HTTPException(
                status_code=401,
                detail="A verified bearer token is required to access this session.",
            )
        if str(authenticated_user_id) != owner_user_id:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to access this session.",
            )
    else:
        # Anonymous session: authenticated user cannot inspect an anonymous session
        if authenticated_user_id is not None:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to access this session.",
            )

    values = checkpoint.values if has_checkpoint else {}
    # Reuse the message endpoint's delivery gate so a held report cannot be
    # recovered through this secondary session-state read path.
    delivery_held = (
        build_message_response(session_id, values).delivery_hold
        if has_checkpoint
        else True
    )
    return SessionDetailResponse(
        session_id=session_id,
        status="completed" if (db_session and db_session.ended_at) else "active",
        intent=values.get("intent") or (db_session.intent if db_session else None),
        messages=[] if delivery_held else values.get("messages", []),
        citations=[] if delivery_held else values.get("retrieved_facts", []),
        calculator_outputs=(
            {} if delivery_held else values.get("calculator_outputs", {})
        ),
    )
