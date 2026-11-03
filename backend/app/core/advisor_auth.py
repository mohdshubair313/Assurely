"""Verified identities authorized separately for advisor report review."""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException

from app.core.config import get_settings
from app.core.security import require_authenticated_user_id
from app.db.policy_review_store import Reviewer


def require_advisor(
    subject: Annotated[uuid.UUID, Depends(require_authenticated_user_id)],
) -> Reviewer:
    settings = get_settings()
    try:
        allowed = {uuid.UUID(value) for value in settings.advisor_subjects}
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(503, "Advisor authorization is not configured.") from exc
    if not allowed or not settings.auth_issuer.strip():
        raise HTTPException(503, "Advisor authorization is not configured.")
    if subject not in allowed:
        raise HTTPException(403, "Advisor authorization is required.")
    return Reviewer(subject=subject, issuer=settings.auth_issuer.strip())
