"""Transactional, append-only policy review staging and blocked import checks."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.policy_rule_draft import PolicyRuleDraft, assess_draft
from app.models.db.policy_review import (
    PolicyReviewDraft,
    PolicyReviewEvent,
    PolicyReviewFact,
    PolicySourceBlob,
    PolicyWorkflowReceipt,
)


@dataclass(frozen=True)
class Reviewer:
    subject: uuid.UUID
    issuer: str


class WorkflowError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(message)


class ReviewCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_key: uuid.UUID
    expected_revision: int = Field(strict=True, ge=0)
    action: Literal["accept_representation", "reject", "revoke"]
    reason: str = Field(min_length=1, max_length=2000)
    expires_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def expiry_scope(self) -> ReviewCommand:
        if (self.action == "accept_representation") != (self.expires_at is not None):
            raise ValueError("Only representation acceptance requires an expiry")
        return self


def _hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


async def _replay(
    db: AsyncSession,
    actor: Reviewer,
    key: uuid.UUID,
    request_hash: str,
) -> dict[str, Any] | None:
    if not db.in_transaction():
        raise RuntimeError("An explicit transaction is required")
    lock = int.from_bytes(
        hashlib.sha256(
            f"{actor.issuer}|{actor.subject}|{key}".encode(),
        ).digest()[:8],
        "big",
        signed=True,
    )
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
    row = await db.get(PolicyWorkflowReceipt, (actor.issuer, actor.subject, key))
    if row:
        if row.request_hash != request_hash:
            raise WorkflowError(409, "Idempotency key belongs to a different request.")
        return row.result
    return None


def _record(
    db: AsyncSession,
    actor: Reviewer,
    key: uuid.UUID,
    request_hash: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    db.add(
        PolicyWorkflowReceipt(
            issuer=actor.issuer,
            actor_id=actor.subject,
            request_key=key,
            request_hash=request_hash,
            result=result,
            created_at=datetime.now(UTC),
        )
    )
    return result


async def stage_draft(
    db: AsyncSession,
    actor: Reviewer,
    key: uuid.UUID,
    raw: str,
    sources: dict[str, bytes],
) -> dict[str, Any]:
    now = datetime.now(UTC)
    preview = await asyncio.to_thread(assess_draft, raw, sources, as_of=now.date())
    draft = PolicyRuleDraft.model_validate_json(raw)
    digest = preview["draft_sha256"]
    fingerprint = _hash(["stage", digest])
    replay = await _replay(db, actor, key, fingerprint)
    if replay is not None:
        return replay
    # Sorted source insertion avoids inverse-order locks between concurrent drafts.
    for source in sorted(draft.source_package.sources, key=lambda s: s.sha256):
        await db.execute(
            insert(PolicySourceBlob)
            .values(
                sha256=source.sha256,
                content=sources[source.id],
            )
            .on_conflict_do_nothing(index_elements=[PolicySourceBlob.sha256])
        )
    inserted = (
        await db.execute(
            insert(PolicyReviewDraft)
            .values(
                digest=digest,
                payload=json.loads(draft.model_dump_json()),
                created_at=now,
                created_by=actor.subject,
                issuer=actor.issuer,
            )
            .on_conflict_do_nothing(index_elements=[PolicyReviewDraft.digest])
            .returning(PolicyReviewDraft.digest)
        )
    ).scalar_one_or_none()
    if inserted:
        originals: dict[str, Any] = {
            f.name: f.model_dump(mode="json") for f in draft.source_package.fields
        }
        db.add_all(
            [
                PolicyReviewFact(
                    draft_digest=digest,
                    name=f.name,
                    payload={"normalized": f.model_dump(mode="json"), "source": originals[f.name]},
                )
                for f in draft.fields
            ]
        )
    return _record(
        db,
        actor,
        key,
        fingerprint,
        {
            "status": "staged",
            "draft_digest": digest,
            "production_approved": False,
            "approved_for_import": False,
        },
    )


async def _locked_draft(db: AsyncSession, digest: str) -> PolicyReviewDraft:
    row = (
        await db.execute(
            select(PolicyReviewDraft)
            .where(
                PolicyReviewDraft.digest == digest,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise WorkflowError(404, "Policy review draft not found.")
    return row


async def _revalidate(db: AsyncSession, row: PolicyReviewDraft) -> dict[str, Any]:
    raw = json.dumps(row.payload)
    draft = PolicyRuleDraft.model_validate_json(raw)
    blobs = (
        await db.scalars(
            select(PolicySourceBlob).where(
                PolicySourceBlob.sha256.in_(
                    {s.sha256 for s in draft.source_package.sources},
                )
            )
        )
    ).all()
    by_hash = {b.sha256: b.content for b in blobs}
    try:
        sources = {s.id: by_hash[s.sha256] for s in draft.source_package.sources}
    except KeyError as exc:
        raise WorkflowError(409, "Pinned source bytes are unavailable.") from exc
    preview = await asyncio.to_thread(assess_draft, raw, sources, as_of=datetime.now(UTC).date())
    if preview["draft_sha256"] != row.digest:
        raise WorkflowError(409, "Stored draft integrity check failed.")
    return preview


async def _latest(db: AsyncSession, digest: str) -> PolicyReviewEvent | None:
    return (
        await db.execute(
            select(PolicyReviewEvent)
            .where(
                PolicyReviewEvent.draft_digest == digest,
            )
            .order_by(PolicyReviewEvent.revision.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _review_state(event: PolicyReviewEvent | None) -> str:
    if event is None:
        return "pending"
    if event.action == "accept_representation":
        if event.expires_at is None or event.expires_at <= datetime.now(UTC):
            return "expired"
        return "representation_accepted"
    return "revoked" if event.action == "revoke" else "rejected"


async def review_draft(
    db: AsyncSession,
    actor: Reviewer,
    digest: str,
    command: ReviewCommand,
) -> dict[str, Any]:
    fingerprint = _hash(["review", digest, command.model_dump(mode="json")])
    replay = await _replay(db, actor, command.request_key, fingerprint)
    if replay is not None:
        return replay  # Historical decision receipt; not a current permission.
    row = await _locked_draft(db, digest)
    latest = await _latest(db, digest)
    revision = latest.revision if latest else 0
    if command.expected_revision != revision:
        raise WorkflowError(409, "Review revision changed; reload the draft.")
    now = datetime.now(UTC)
    if command.expires_at is not None and not now < command.expires_at <= now + timedelta(days=90):
        raise WorkflowError(422, "Review expiry must be in the future and within 90 days.")
    if command.action == "revoke" and (latest is None or latest.action != "accept_representation"):
        raise WorkflowError(409, "No representation acceptance is available to revoke.")
    if command.action == "accept_representation":
        await _revalidate(db, row)
    event_id = uuid.uuid4()
    db.add(
        PolicyReviewEvent(
            id=event_id,
            draft_digest=digest,
            revision=revision + 1,
            action=command.action,
            reason=command.reason,
            reviewer_id=actor.subject,
            issuer=actor.issuer,
            created_at=now,
            expires_at=command.expires_at,
        )
    )
    return _record(
        db,
        actor,
        command.request_key,
        fingerprint,
        {
            "event_id": str(event_id),
            "draft_digest": digest,
            "revision": revision + 1,
            "action": command.action,
            "scope": "representation_only",
            "recorded_at": now.isoformat(),
            "approved_for_import": False,
            "production_approved": False,
        },
    )


async def check_import(
    db: AsyncSession,
    actor: Reviewer,
    digest: str,
    key: uuid.UUID,
) -> dict[str, Any]:
    fingerprint = _hash(["import_check", digest])
    replay = await _replay(db, actor, key, fingerprint)
    if replay is not None:
        return replay
    row = await _locked_draft(db, digest)
    preview = await _revalidate(db, row)
    event = await _latest(db, digest)
    return _record(
        db,
        actor,
        key,
        fingerprint,
        {
            "status": "blocked",
            "scope": "import_diagnostics_only",
            "checked_at": datetime.now(UTC).isoformat(),
            "representation_review": _review_state(event),
            "review_revision": event.revision if event else 0,
            **preview,
        },
    )


async def read_draft(db: AsyncSession, digest: str) -> dict[str, Any]:
    row = await _locked_draft(db, digest)
    events = (
        await db.scalars(
            select(PolicyReviewEvent)
            .where(
                PolicyReviewEvent.draft_digest == digest,
            )
            .order_by(PolicyReviewEvent.revision)
        )
    ).all()
    return {
        "draft_digest": digest,
        "draft": row.payload,
        "representation_review": _review_state(events[-1] if events else None),
        "revision": events[-1].revision if events else 0,
        "events": [
            {
                "id": str(e.id),
                "revision": e.revision,
                "action": e.action,
                "reason": e.reason,
                "reviewer_id": str(e.reviewer_id),
                "issuer": e.issuer,
                "created_at": e.created_at.isoformat(),
                "expires_at": e.expires_at.isoformat() if e.expires_at else None,
            }
            for e in events
        ],
        "approved_for_import": False,
        "production_approved": False,
    }
