"""Verified self context and narrow, audited operator controls."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.core.consent import CONSENT_PURPOSES, CONSENT_VERSION
from app.core.security import AuthenticatedPrincipal, require_admin, require_principal, server_roles
from app.db.session import AsyncSessionLocal
from app.models.db.auth_identity import AuthEvent
from app.models.db.consent_record import ConsentRecord
from app.models.db.escalation import Escalation
from app.models.db.user import User

router = APIRouter()
Principal = Annotated[AuthenticatedPrincipal, Depends(require_principal)]
Admin = Annotated[AuthenticatedPrincipal, Depends(require_admin)]


@router.get("/me")
async def me(principal: Principal) -> dict[str, Any]:
    return {"user_id": str(principal.user_id), "roles": sorted(principal.roles),
            "provider": principal.provider}


@router.get("/me/consents")
async def consents(principal: Principal) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        rows = (await db.scalars(select(ConsentRecord).where(
            ConsentRecord.user_id == principal.user_id,
            ConsentRecord.revoked_at.is_(None),
        ))).all()
    active = {row.scope: row for row in rows}
    return {"purpose_version": CONSENT_VERSION, "purposes": [
        {"scope": scope, "description": description,
         "granted": scope in active and active[scope].purpose_version == CONSENT_VERSION,
         "granted_at": active[scope].granted_at.isoformat() if scope in active else None}
        for scope, description in CONSENT_PURPOSES.items()
    ]}


class Assignment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    advisor_id: uuid.UUID
    reason: str = Field(min_length=1, max_length=1000)


@router.post("/admin/escalations/{escalation_id}/assign")
async def assign(escalation_id: uuid.UUID, command: Assignment, admin: Admin) -> dict[str, Any]:
    if "human_advisor" not in server_roles(command.advisor_id):
        raise HTTPException(403, "The assignee must be an authorized human advisor.")
    async with AsyncSessionLocal() as db, db.begin():
        escalation = await db.scalar(select(Escalation).where(
            Escalation.id == escalation_id).with_for_update())
        if escalation is None:
            raise HTTPException(404, "Escalation not found.")
        if await db.get(User, command.advisor_id) is None:
            raise HTTPException(409, "The advisor identity must be provisioned first.")
        if escalation.status == "resolved":
            raise HTTPException(409, "A resolved escalation cannot be reassigned.")
        escalation.assigned_advisor = command.advisor_id
        escalation.status = "assigned"
        db.add(AuthEvent(id=uuid.uuid4(), user_id=admin.user_id, action="escalation_assigned",
                        details={"escalation_id": str(escalation_id),
                                 "advisor_id": str(command.advisor_id), "reason": command.reason,
                                 "issuer": admin.issuer}))
    return {"escalation_id": str(escalation_id), "status": "assigned",
            "delivery_authorized": False}
