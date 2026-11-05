"""Restrict policy review to verified subjects explicitly authorized by the operator."""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException

from app.core.config import get_settings
from app.core.security import is_test_account, require_authenticated_user_id
from app.db.policy_review_store import Reviewer


def require_policy_reviewer(
    subject: Annotated[uuid.UUID, Depends(require_authenticated_user_id)],
) -> Reviewer:
    settings = get_settings()
    try:
        allowed = {uuid.UUID(item) for item in settings.policy_reviewer_subjects}
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(503, "Policy-review authorization is not configured.") from exc
    if not allowed or not settings.auth_issuer.strip():
        raise HTTPException(503, "Policy-review authorization is not configured.")
    if subject not in allowed:
        raise HTTPException(403, "Policy-review authorization is required.")
    if is_test_account(subject):
        raise HTTPException(403, "Test accounts cannot approve policy evidence.")
    return Reviewer(subject=subject, issuer=settings.auth_issuer.strip())


def require_policy_publisher(
    subject: Annotated[uuid.UUID, Depends(require_authenticated_user_id)],
) -> Reviewer:
    settings = get_settings()
    try:
        allowed = {uuid.UUID(item) for item in settings.policy_publisher_subjects}
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(503, "Policy-publication authorization is not configured.") from exc
    if not allowed or not settings.auth_issuer.strip():
        raise HTTPException(503, "Policy-publication authorization is not configured.")
    if subject not in allowed:
        raise HTTPException(403, "Policy-publication authorization is required.")
    if is_test_account(subject):
        raise HTTPException(403, "Test accounts cannot publish policy evidence.")
    return Reviewer(subject=subject, issuer=settings.auth_issuer.strip())
