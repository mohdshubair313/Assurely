"""Protected proposal, publication and fresh applicability-check APIs."""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.v1.policy_reviews import Actor, Database, Digest, _body
from app.core.policy_review_auth import require_policy_publisher
from app.db import policy_publication_store as store
from app.db import reviewed_comparison, reviewed_policy_terms
from app.db.policy_publication_contract import Capability, LookupContext
from app.db.policy_review_store import Reviewer, WorkflowError
from app.db.source_review import ClosedModel

router = APIRouter(prefix="/policy-publications")
Publisher = Annotated[Reviewer, Depends(require_policy_publisher)]


class LookupCommand(ClosedModel):
    capability: Capability
    context: LookupContext


@router.post("/comparisons")
async def compare(request: Request, actor: Actor, db: Database) -> dict[str, Any]:
    """Compare explicitly scoped reviewed facts for an authorized operator."""
    try:
        command = reviewed_comparison.ComparisonRequest.model_validate_json(
            json.dumps(await _body(request, 64 * 1024))
        )
        return await reviewed_comparison.compare(db, actor, command)
    except WorkflowError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, "Invalid reviewed comparison request.") from exc


@router.get("/requirements/{digest}")
async def requirements(digest: Digest, actor: Actor, db: Database) -> dict[str, Any]:
    try:
        return await store.requirements(db, actor, digest)
    except WorkflowError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, "Stored source evidence could not be validated.") from exc


@router.post("")
async def propose(request: Request, actor: Actor, db: Database) -> dict[str, Any]:
    try:
        command = store.ProposeCommand.model_validate_json(
            json.dumps(await _body(request, 512_000))
        )
        return await store.propose(db, actor, command)
    except WorkflowError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, "Invalid publication manifest or source evidence.") from exc


@router.get("/{digest}")
async def read(digest: Digest, actor: Actor, db: Database) -> dict[str, Any]:
    try:
        return await store.read(db, actor, digest)
    except WorkflowError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, "Stored publication integrity check failed.") from exc


@router.post("/{digest}/decisions")
async def decide(
    digest: Digest, request: Request, actor: Publisher, db: Database
) -> dict[str, Any]:
    try:
        command = store.PublishCommand.model_validate_json(json.dumps(await _body(request, 16_384)))
        return await store.decide(db, actor, digest, command)
    except WorkflowError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, "Invalid publication decision or source evidence.") from exc


@router.post("/{digest}/term-import")
async def term_import(
    digest: Digest, request: Request, actor: Publisher, db: Database
) -> dict[str, Any]:
    try:
        command = reviewed_policy_terms.ImportCommand.model_validate_json(
            json.dumps(await _body(request, 16_384))
        )
        return await reviewed_policy_terms.import_terms(db, actor, digest, command)
    except WorkflowError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, "Invalid reviewed term import or source evidence.") from exc


@router.post("/{digest}/lookup")
async def lookup(digest: Digest, request: Request, actor: Actor, db: Database) -> dict[str, Any]:
    try:
        command = LookupCommand.model_validate_json(json.dumps(await _body(request, 16_384)))
        return await store.lookup(
            db,
            issuer=actor.issuer,
            digest=digest,
            capability=command.capability,
            context=command.context,
        )
    except WorkflowError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, "Invalid applicability request or source evidence.") from exc
