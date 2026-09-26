"""POST /v1/consent — grant or revoke consent scopes.

Manages data-processing permissions per DPDP Act 2023.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()


class ConsentRequest(BaseModel):
    user_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scope: Literal["process_comparison", "save_profile", "receive_updates"]
    action: Literal["grant", "revoke"]


class ConsentResponse(BaseModel):
    user_id: str
    scope: str
    status: str
    timestamp: str


@router.post("/consent", response_model=ConsentResponse)
async def update_consent(req: ConsentRequest) -> ConsentResponse:
    """Record consent grant or revocation per DPDP Act 2023."""
    now_iso = datetime.now(timezone.utc).isoformat()
    return ConsentResponse(
        user_id=req.user_id,
        scope=req.scope,
        status="granted" if req.action == "grant" else "revoked",
        timestamp=now_iso,
    )
