"""GET /v1/session/{id} — retrieve session details.

Powers the "why am I seeing this" explainability view and the audit trail.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()


class SessionDetailResponse(BaseModel):
    session_id: str
    status: str
    intent: str | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    calculator_outputs: dict[str, Any] = Field(default_factory=dict)


@router.get("/session/{session_id}", response_model=SessionDetailResponse)
async def get_session(session_id: str) -> SessionDetailResponse:
    """Retrieve session audit state."""
    return SessionDetailResponse(
        session_id=session_id,
        status="active",
        intent="health",
        messages=[],
        citations=[],
        calculator_outputs={},
    )
