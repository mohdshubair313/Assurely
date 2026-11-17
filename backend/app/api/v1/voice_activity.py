"""Owner-only development receipt projection with no provider side effects."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response

from app.core.config import get_settings
from app.core.security import require_authenticated_user_id
from app.db.session import AsyncSessionLocal
from app.voice.activity import ActivityRecapService

router = APIRouter(prefix="/voice/development")
Owner = Annotated[uuid.UUID, Depends(require_authenticated_user_id)]


@router.get("/sessions/{session_id}/activity-recap")
async def activity_recap(session_id: uuid.UUID, owner: Owner, response: Response) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    return await ActivityRecapService(AsyncSessionLocal, get_settings()).read_activity(
        owner, session_id
    )
