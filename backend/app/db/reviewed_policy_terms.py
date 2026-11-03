"""Explicit, audited import and gated reads of reviewed policy_terms records."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import policy_publication_store as publication
from app.db import policy_review_store as review
from app.db.policy_publication_contract import (
    REQUIRED,
    Capability,
    LookupContext,
    PublicationManifest,
)
from app.db.policy_rule_draft import PolicyRuleDraft
from app.db.source_review import ClosedModel
from app.models.db.policy_review import PolicyReviewDraft
from app.models.db.policy_terms import PolicyTerms


class ImportCommand(ClosedModel):
    request_key: uuid.UUID
    publication_event_id: uuid.UUID


def _snapshot(draft: PolicyRuleDraft, manifest: PublicationManifest) -> dict[str, Any]:
    fields = {field.name: field for field in draft.fields}
    facts: dict[str, dict[str, Any]] = {}
    for scope in manifest.scopes:
        for name in REQUIRED[scope.capability]:
            value = fields[name].value
            if value is None or fields[name].status != "proposed":
                raise ValueError("Missing reviewed policy fact")
            encoded = value.model_dump(mode="json")
            if encoded["kind"] == "age":
                encoded["age_basis"] = scope.age_basis
            facts[name] = encoded
    return {
        "format": "reviewed-policy-terms-v1",
        "draft_digest": manifest.draft_digest,
        "facts": facts,
    }


async def import_terms(
    db: AsyncSession, actor: review.Reviewer, digest: str, command: ImportCommand
) -> dict[str, Any]:
    """Copy exact reviewed values atomically with an actor-bound historical receipt."""
    fingerprint = review._hash(["reviewed_terms_import", digest, command.model_dump(mode="json")])
    replay = await review._replay(db, actor, command.request_key, fingerprint)
    if replay is not None:
        return replay
    row = await publication._row(db, digest, actor.issuer)
    await publication._scope_lock(db, row.identity_key)
    draft_row = await review._locked_draft(db, row.draft_digest)
    state, event = await publication._state(db, row)
    if state != "published" or event is None or event.id != command.publication_event_id:
        raise review.WorkflowError(409, "A current matching publication decision is required.")
    manifest = publication._manifest(row)
    await publication._validate(db, draft_row, manifest)
    draft = PolicyRuleDraft.model_validate_json(json.dumps(draft_row.payload))
    snapshot = _snapshot(draft, manifest)
    # Validation may be long; an expiry during validation must not allow import.
    state, current = await publication._state(db, row)
    if state != "published" or current is None or current.id != event.id:
        raise review.WorkflowError(409, "Publication expired or changed before import.")
    await db.execute(
        insert(PolicyTerms)
        .values(
            id=uuid.uuid4(),
            record_kind="reviewed_v1",
            publication_digest=digest,
            version_hash=digest,
            reviewed_facts_json=snapshot,
            policy_document_id=None,
            effective_date=None,
        )
        .on_conflict_do_nothing(index_elements=[PolicyTerms.publication_digest])
    )
    terms = await db.scalar(select(PolicyTerms).where(PolicyTerms.publication_digest == digest))
    if (
        terms is None
        or terms.record_kind != "reviewed_v1"
        or terms.version_hash != digest
        or terms.reviewed_facts_json != snapshot
    ):
        raise review.WorkflowError(409, "Reviewed policy term integrity check failed.")
    return review._record(
        db,
        actor,
        command.request_key,
        fingerprint,
        {
            "status": "imported",
            "policy_terms_id": str(terms.id),
            "publication_digest": digest,
            "publication_event_id": str(event.id),
            "scope": "historical_import_receipt",
            "requires_fresh_lookup": True,
        },
    )


async def lookup_terms(
    db: AsyncSession, *, issuer: str, digest: str, capability: Capability, context: LookupContext
) -> dict[str, Any]:
    """Recheck publication and return exact values loaded from the policy_terms row."""
    outcome = await publication.lookup(
        db,
        issuer=issuer,
        digest=digest,
        capability=capability,
        context=context,
    )
    if outcome["status"] != "available":
        return outcome
    terms = await db.scalar(
        select(PolicyTerms).where(
            PolicyTerms.publication_digest == digest, PolicyTerms.record_kind == "reviewed_v1"
        )
    )
    if terms is None:
        return {
            "publication_digest": digest,
            "capability": capability,
            "status": "unavailable",
            "reason": "terms_not_imported",
            "facts": [],
        }
    # The publication row and draft remain locked by lookup. Reconstruct the
    # complete expected snapshot rather than trusting the stored JSON or receipt.
    row = await publication._row(db, digest, issuer)
    manifest = publication._manifest(row)
    draft_row = await db.get(PolicyReviewDraft, row.draft_digest)
    if draft_row is None:
        raise review.WorkflowError(409, "Reviewed policy draft is unavailable.")
    draft = PolicyRuleDraft.model_validate_json(json.dumps(draft_row.payload))
    expected = _snapshot(draft, manifest)
    if terms.version_hash != digest or terms.reviewed_facts_json != expected:
        raise review.WorkflowError(409, "Reviewed policy term integrity check failed.")
    for fact in outcome["facts"]:
        fact["value"] = terms.reviewed_facts_json["facts"][fact["name"]]
        fact["policy_terms_id"] = str(terms.id)
    outcome["policy_terms_id"] = str(terms.id)
    outcome["storage_scope"] = "reviewed_policy_terms"
    # Check expiration again after reading and validating the stored snapshot.
    state, _ = await publication._state(db, row)
    if state != "published":
        return {
            "publication_digest": digest,
            "capability": capability,
            "status": "unavailable",
            "reason": state,
            "facts": [],
        }
    return outcome
