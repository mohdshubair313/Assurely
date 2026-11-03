"""Authenticated internal policy-review staging; no policy publication endpoint."""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.policy_review_auth import require_policy_reviewer
from app.db import policy_review_store as store
from app.db.policy_rule_draft import _unique_object

router = APIRouter(prefix="/policy-reviews")


class StageCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: uuid.UUID
    draft_json: str = Field(min_length=1, max_length=512_000)
    sources_base64: dict[str, str] = Field(min_length=1, max_length=20)


class CheckCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: uuid.UUID


async def review_db() -> AsyncIterator[AsyncSession]:
    # Lazy import: importing this router never loads a database connection or .env.
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db, db.begin():
        yield db


Actor = Annotated[store.Reviewer, Depends(require_policy_reviewer)]
Database = Annotated[AsyncSession, Depends(review_db)]
Digest = Annotated[str, Path(pattern=r"^[a-f0-9]{64}$")]


async def _body(request: Request, limit: int) -> Any:
    body = bytearray()
    async for part in request.stream():
        body.extend(part)
        if len(body) > limit:
            raise HTTPException(413, "Policy-review upload exceeds the size limit.")
    return json.loads(body, object_pairs_hook=_unique_object)


@router.post("/drafts")
async def stage(request: Request, actor: Actor, db: Database) -> dict[str, Any]:
    # Only an authorized operator reaches body parsing; bound aggregate input too.
    try:
        decoded = await _body(request, 60 * 1024 * 1024)
        command = StageCommand.model_validate(decoded)
        sources = {}
        for key, value in command.sources_base64.items():
            if len(value) > 28 * 1024 * 1024:
                raise HTTPException(413, "Policy source exceeds the size limit.")
            content = base64.b64decode(value, validate=True)
            if len(content) > 20 * 1024 * 1024:
                raise HTTPException(413, "Policy source exceeds the size limit.")
            sources[key] = content
        return await store.stage_draft(db, actor, command.request_key, command.draft_json, sources)
    except store.WorkflowError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    except (ValueError, ValidationError, binascii.Error) as exc:
        # Do not echo uploaded policy contents or embedded instructions in errors.
        raise HTTPException(422, "Invalid policy-review draft or source evidence.") from exc


@router.get("/drafts/{digest}")
async def read(digest: Digest, actor: Actor, db: Database) -> dict[str, Any]:
    try:
        return await store.read_draft(db, digest)
    except store.WorkflowError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


@router.post("/drafts/{digest}/reviews")
async def review(
    digest: Digest,
    request: Request,
    actor: Actor,
    db: Database,
) -> dict[str, Any]:
    try:
        command = store.ReviewCommand.model_validate(await _body(request, 16 * 1024))
        return await store.review_draft(db, actor, digest, command)
    except store.WorkflowError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, "Invalid review request or stored source evidence.") from exc


@router.post("/drafts/{digest}/import-checks")
async def import_check(
    digest: Digest,
    request: Request,
    actor: Actor,
    db: Database,
) -> dict[str, Any]:
    try:
        command = CheckCommand.model_validate(await _body(request, 16 * 1024))
        return await store.check_import(db, actor, digest, command.request_key)
    except store.WorkflowError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, "Stored source evidence could not be validated.") from exc
