"""Transactional publication gate and fresh, fail-closed deterministic fact lookup.

Callers supply a verified operator principal, never identity fields from JSON.
Every mutation requires an explicit transaction. Receipts are historical, not tokens.
"""

from __future__ import annotations

import asyncio
import json
import unicodedata
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import AwareDatetime, Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import policy_review_store as review
from app.db.policy_publication_contract import (
    REQUIRED,
    Capability,
    LookupContext,
    PublicationManifest,
    applicability_result,
    identity,
    note_id,
    validate_evidence,
    validate_manifest,
)
from app.db.policy_rule_draft import PolicyRuleDraft
from app.db.source_review import ClosedModel, Text
from app.models.db.policy_publication import PolicyPublication, PolicyPublicationEvent
from app.models.db.policy_review import PolicyReviewDraft, PolicySourceBlob


class ProposeCommand(ClosedModel):
    request_key: uuid.UUID
    manifest: PublicationManifest


class PublishCommand(ClosedModel):
    request_key: uuid.UUID
    expected_revision: int = Field(strict=True, ge=0)
    representation_event_id: uuid.UUID
    action: Literal["publish", "revoke"]
    reason: Text
    expires_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def expiry_scope(self) -> PublishCommand:
        if (self.action == "publish") != (self.expires_at is not None):
            raise ValueError("Only publication requires an expiry")
        if len(self.reason) > 2000:
            raise ValueError("Decision reason exceeds limit")
        return self


async def requirements(db: AsyncSession, actor: review.Reviewer, digest: str) -> dict[str, Any]:
    """Expose exact note identities so operators can prepare a reviewable manifest."""
    row = await review._locked_draft(db, digest)
    if row.issuer != actor.issuer:
        raise review.WorkflowError(404, "Policy review draft not found.")
    await review._revalidate(db, row)
    draft = PolicyRuleDraft.model_validate_json(json.dumps(row.payload))
    fields = {f.name: f for f in draft.fields}
    return {
        "draft_digest": digest,
        "production_approved": False,
        "supported_capabilities": {
            name: {
                "required_fields": sorted(names),
                "missing_typed_fields": sorted(n for n in names if fields[n].status != "proposed"),
            }
            for name, names in REQUIRED.items()
        },
        "identity_fields": ["uin", "variant", "effective_date", "expiry_date"],
        "notes": [
            {
                "field": f.name,
                "kind": kind,
                "text": note,
                "note_sha256": note_id(f.name, kind, index, note),
            }
            for f in draft.source_package.fields
            for kind in ("conditions", "unresolved")
            for index, note in enumerate(getattr(f, kind))
        ],
    }


def _manifest(row: PolicyPublication) -> PublicationManifest:
    manifest = PublicationManifest.model_validate_json(json.dumps(row.payload))
    if review._hash(manifest.model_dump(mode="json")) != row.digest:
        raise review.WorkflowError(409, "Publication integrity check failed.")
    return manifest


async def _scope_lock(db: AsyncSession, identity_key: str) -> None:
    if not db.in_transaction():
        raise RuntimeError("An explicit transaction is required")
    key = int.from_bytes(bytes.fromhex(identity_key)[:8], "big", signed=True)
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


async def _row(db: AsyncSession, digest: str, issuer: str) -> PolicyPublication:
    row = await db.get(PolicyPublication, digest)
    if row is None or row.issuer != issuer:
        raise review.WorkflowError(404, "Policy publication not found.")
    return row


async def _latest(db: AsyncSession, digest: str) -> PolicyPublicationEvent | None:
    return await db.scalar(
        select(PolicyPublicationEvent)
        .where(PolicyPublicationEvent.publication_digest == digest)
        .order_by(PolicyPublicationEvent.revision.desc())
        .limit(1)
    )


async def _validate(
    db: AsyncSession, row: PolicyReviewDraft, manifest: PublicationManifest
) -> None:
    if manifest.draft_digest != row.digest:
        raise review.WorkflowError(409, "Publication is bound to a different draft.")
    await review._revalidate(db, row)
    draft = PolicyRuleDraft.model_validate_json(json.dumps(row.payload))
    validate_manifest(manifest, draft)
    blobs = (
        await db.scalars(
            select(PolicySourceBlob).where(
                PolicySourceBlob.sha256.in_({s.sha256 for s in draft.source_package.sources})
            )
        )
    ).all()
    await asyncio.to_thread(
        validate_evidence, manifest, draft, {b.sha256: b.content for b in blobs}
    )


async def propose(
    db: AsyncSession, actor: review.Reviewer, command: ProposeCommand
) -> dict[str, Any]:
    manifest = command.manifest
    payload = manifest.model_dump(mode="json")
    digest = review._hash(payload)
    fingerprint = review._hash(["publication_proposal", digest])
    replay = await review._replay(db, actor, command.request_key, fingerprint)
    if replay is not None:
        return replay
    draft_row = await review._locked_draft(db, manifest.draft_digest)
    if draft_row.issuer != actor.issuer:
        raise review.WorkflowError(404, "Policy review draft not found.")
    await _validate(db, draft_row, manifest)
    draft = PolicyRuleDraft.model_validate_json(json.dumps(draft_row.payload))
    # Marketing-label spelling must not bypass the overlap lock. UIN + exact
    # variant scope identify the publication family; normalize cosmetic differences.
    _, _, uin, variant = identity(draft)
    canonical = [
        " ".join(unicodedata.normalize("NFKC", s).casefold().split()) for s in (uin, variant)
    ]
    identity_key = review._hash([actor.issuer, *canonical])
    await db.execute(
        insert(PolicyPublication)
        .values(
            digest=digest,
            draft_digest=draft_row.digest,
            identity_key=identity_key,
            payload=payload,
            created_by=actor.subject,
            issuer=actor.issuer,
            created_at=datetime.now(UTC),
        )
        .on_conflict_do_nothing(index_elements=[PolicyPublication.digest])
    )
    return review._record(
        db,
        actor,
        command.request_key,
        fingerprint,
        {
            "publication_digest": digest,
            "status": "proposed",
            "production_approved": False,
        },
    )


async def _state(
    db: AsyncSession, row: PolicyPublication
) -> tuple[str, PolicyPublicationEvent | None]:
    event = await _latest(db, row.digest)
    if event is None:
        return "pending", None
    if event.action != "publish":
        return "revoked", event
    now = datetime.now(UTC)
    if event.expires_at is None or event.expires_at <= now:
        return "expired", event
    representation = await review._latest(db, row.draft_digest)
    if (
        representation is None
        or representation.id != event.representation_event_id
        or review._review_state(representation) != "representation_accepted"
        or representation.issuer != row.issuer
    ):
        return "representation_invalidated", event
    return "published", event


def _overlaps(left: PublicationManifest, right: PublicationManifest) -> bool:
    a, b = left.applicability, right.applicability
    if (
        a.cover_basis != b.cover_basis
        or a.date_basis != b.date_basis
        or set(a.selected_options) != set(b.selected_options)
    ):
        return False
    if not {s.capability for s in left.scopes} & {s.capability for s in right.scopes}:
        return False
    # Conservatively reject overlaps even if predicates might distinguish scopes.
    return (a.window.end is None or b.window.start <= a.window.end) and (
        b.window.end is None or a.window.start <= b.window.end
    )


async def decide(
    db: AsyncSession, actor: review.Reviewer, digest: str, command: PublishCommand
) -> dict[str, Any]:
    fingerprint = review._hash(["publication_decision", digest, command.model_dump(mode="json")])
    replay = await review._replay(db, actor, command.request_key, fingerprint)
    if replay is not None:
        return replay
    row = await _row(db, digest, actor.issuer)
    await _scope_lock(db, row.identity_key)
    # All publication decisions lock identity then draft; representation review only locks draft.
    draft_row = await review._locked_draft(db, row.draft_digest)
    latest = await _latest(db, digest)
    revision = latest.revision if latest else 0
    if revision != command.expected_revision:
        raise review.WorkflowError(409, "Publication revision changed; reload the publication.")
    now = datetime.now(UTC)
    if command.action == "publish":
        if actor.subject in {row.created_by, draft_row.created_by}:
            raise review.WorkflowError(
                403, "A different authorized publisher must review this proposal."
            )
        representation = await review._latest(db, row.draft_digest)
        if (
            representation is None
            or representation.id != command.representation_event_id
            or representation.issuer != actor.issuer
            or review._review_state(representation) != "representation_accepted"
        ):
            raise review.WorkflowError(409, "A current, exact representation review is required.")
        assert representation.expires_at is not None
        if command.expires_at is None or not now < command.expires_at <= min(
            now + timedelta(days=90), representation.expires_at
        ):
            raise review.WorkflowError(422, "Publication expiry exceeds its review validity.")
        manifest = _manifest(row)
        await _validate(db, draft_row, manifest)
        others = (
            await db.scalars(
                select(PolicyPublication).where(
                    PolicyPublication.identity_key == row.identity_key,
                    PolicyPublication.digest != digest,
                )
            )
        ).all()
        for other in others:
            state, _ = await _state(db, other)
            if state == "published" and _overlaps(manifest, _manifest(other)):
                raise review.WorkflowError(409, "An overlapping capability is already published.")
    elif (
        latest is None
        or latest.action != "publish"
        or command.representation_event_id != latest.representation_event_id
    ):
        raise review.WorkflowError(409, "No matching publication is available to revoke.")
    event_id = uuid.uuid4()
    db.add(
        PolicyPublicationEvent(
            id=event_id,
            publication_digest=digest,
            revision=revision + 1,
            representation_event_id=command.representation_event_id,
            action=command.action,
            reviewer_id=actor.subject,
            issuer=actor.issuer,
            reason=command.reason,
            created_at=now,
            expires_at=command.expires_at,
        )
    )
    return review._record(
        db,
        actor,
        command.request_key,
        fingerprint,
        {
            "event_id": str(event_id),
            "publication_digest": digest,
            "revision": revision + 1,
            "action": command.action,
            "recorded_at": now.isoformat(),
            "scope": "historical_publication_receipt",
            "requires_fresh_lookup": True,
        },
    )


async def read(db: AsyncSession, actor: review.Reviewer, digest: str) -> dict[str, Any]:
    row = await _row(db, digest, actor.issuer)
    await _scope_lock(db, row.identity_key)
    await review._locked_draft(db, row.draft_digest)
    manifest = _manifest(row)
    state, latest = await _state(db, row)
    events = (
        await db.scalars(
            select(PolicyPublicationEvent)
            .where(PolicyPublicationEvent.publication_digest == digest)
            .order_by(PolicyPublicationEvent.revision)
        )
    ).all()
    return {
        "publication_digest": digest,
        "manifest": manifest.model_dump(mode="json"),
        "status": state,
        "revision": latest.revision if latest else 0,
        "scope": "capability_publication_only",
        "checked_at": datetime.now(UTC).isoformat(),
        "events": [
            {
                "id": str(e.id),
                "action": e.action,
                "revision": e.revision,
                "reviewer_id": str(e.reviewer_id),
                "issuer": e.issuer,
                "reason": e.reason,
                "created_at": e.created_at.isoformat(),
                "expires_at": e.expires_at.isoformat() if e.expires_at else None,
            }
            for e in events
        ],
    }


async def lookup(
    db: AsyncSession, *, issuer: str, digest: str, capability: Capability, context: LookupContext
) -> dict[str, Any]:
    """Recheck authority state on every read. Never consult legacy seed terms.

    Context is request input, not a certified customer schedule. Returned facts must
    not be presented as a coverage or eligibility verdict.
    """
    row = await _row(db, digest, issuer)
    await _scope_lock(db, row.identity_key)
    draft_row = await review._locked_draft(db, row.draft_digest)
    state, event = await _state(db, row)
    base: dict[str, Any] = {
        "publication_digest": digest,
        "capability": capability,
        "checked_at": datetime.now(UTC).isoformat(),
        "facts": [],
    }
    if state != "published":
        return {**base, "status": "unavailable", "reason": state}
    assert event is not None
    manifest = _manifest(row)
    # Revalidate bytes and interpretation bindings; corruption never grants facts.
    await _validate(db, draft_row, manifest)
    scope = next((s for s in manifest.scopes if s.capability == capability), None)
    if scope is None:
        return {**base, "status": "unavailable", "reason": "capability_not_published"}
    applicable = applicability_result(manifest, context)
    if applicable != "applicable":
        return {**base, "status": "unavailable", "reason": applicable}
    condition = scope.conditions.evaluate(context.model_dump())
    if condition is not True:
        return {
            **base,
            "status": "unavailable",
            "reason": ("conditions_unknown" if condition is None else "conditions_not_met"),
        }
    # Validation can take time; do not release a record that expired during it.
    state, _ = await _state(db, row)
    if state != "published":
        return {**base, "status": "unavailable", "reason": state}
    draft = PolicyRuleDraft.model_validate_json(json.dumps(draft_row.payload))
    originals: dict[str, Any] = {f.name: f for f in draft.source_package.fields}
    sources = {s.id: s for s in draft.source_package.sources}

    def source_reference(ref: Any) -> dict[str, Any]:
        return {
            **ref.model_dump(mode="json"),
            "url": sources[ref.source_id].url,
            "sha256": sources[ref.source_id].sha256,
        }

    facts = []
    for fact in draft.fields:
        if fact.name not in REQUIRED[capability]:
            continue
        assert fact.value is not None
        value = fact.value.model_dump(mode="json")
        if value["kind"] == "age":
            value["age_basis"] = scope.age_basis
        evidence = [source_reference(ref) for ref in originals[fact.name].references]
        facts.append(
            {
                "name": fact.name,
                "value": value,
                "source": evidence,
                "last_verified": event.created_at.date().isoformat(),
                "verification_event_id": str(event.id),
            }
        )
    return {
        **base,
        "status": "available",
        "facts": facts,
        "identity": list(identity(draft)),
        "verification_scope": "human_reviewed_conditional_product_facts",
        "applicability": manifest.applicability.model_dump(mode="json"),
        "conditions": scope.conditions.model_dump(mode="json"),
        # The original fact citation alone does not substantiate a separate
        # applicability or condition interpretation. Keep their review evidence
        # and resolutions alongside the scoped fact.
        "scope_review": {
            "last_verified": event.created_at.date().isoformat(),
            "verification_event_id": str(event.id),
            "applicability_evidence": [
                source_reference(ref) for ref in manifest.applicability.evidence
            ],
            "condition_evidence": [source_reference(ref) for ref in scope.evidence],
            "identity_note_mappings": [
                {
                    **mapping.model_dump(mode="json"),
                    "evidence": [source_reference(ref) for ref in mapping.evidence],
                }
                for mapping in manifest.identity_notes
            ],
            "condition_note_mappings": [
                {
                    **mapping.model_dump(mode="json"),
                    "evidence": [source_reference(ref) for ref in mapping.evidence],
                }
                for mapping in scope.note_mappings
            ],
        },
        "expires_at": event.expires_at.isoformat() if event.expires_at else None,
    }
