"""Produce an internal, scenario-scoped comparison of freshly reviewed policy facts.

This is a review preview, not a customer report, eligibility decision or release
credential. Each capability goes through the publication service on every request.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import policy_publication_store as publication
from app.db import reviewed_policy_terms
from app.db.policy_publication_contract import Capability, LookupContext
from app.db.policy_review_store import Reviewer, WorkflowError
from app.db.source_review import ClosedModel, Digest
from app.models.db.policy_publication import PolicyPublication


class ComparisonItem(ClosedModel):
    publication_digest: Digest
    capabilities: list[Capability] = Field(min_length=1, max_length=3)
    context: LookupContext

    @model_validator(mode="after")
    def distinct_capabilities(self) -> ComparisonItem:
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("Duplicate capability")
        return self


class ComparisonRequest(ClosedModel):
    items: list[ComparisonItem] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def distinct_publications(self) -> ComparisonRequest:
        digests = [item.publication_digest for item in self.items]
        if len(digests) != len(set(digests)):
            raise ValueError("Duplicate publication")
        return self


def _unavailable(capability: Capability, reason: str) -> dict[str, Any]:
    return {"capability": capability, "status": "unavailable", "reason": reason, "facts": []}


async def compare(db: AsyncSession, actor: Reviewer, request: ComparisonRequest) -> dict[str, Any]:
    """Return the operator's reviewed-source preview."""
    return await _compare(db, actor.issuer, request, require_terms=False)


async def compare_terms(
    db: AsyncSession, issuer: str, request: ComparisonRequest
) -> dict[str, Any]:
    """Prepare graph data only from imported policy_terms and current publications."""
    if not issuer.strip():
        raise ValueError("A configured publication issuer is required")
    return await _compare(db, issuer, request, require_terms=True)


async def _compare(
    db: AsyncSession, issuer: str, request: ComparisonRequest, *, require_terms: bool
) -> dict[str, Any]:
    """Compare only explicitly selected facts, with fresh checks in one transaction.

    Acquire all identity locks in canonical order before any draft locks, matching
    publication's identity-then-draft discipline and avoiding inverse-order waits.
    Return items in caller order; unavailable, expired or invalid data stays empty.
    """
    if not db.in_transaction():
        raise RuntimeError("An explicit transaction is required")
    digests = [item.publication_digest for item in request.items]
    rows = (
        await db.scalars(
            select(PolicyPublication).where(
                PolicyPublication.issuer == issuer,
                PolicyPublication.digest.in_(digests),
            )
        )
    ).all()
    for key in sorted({row.identity_key for row in rows}):
        await publication._scope_lock(db, key)

    result_by_digest: dict[str, dict[str, Any]] = {}
    # Group by identity and then draft, not caller input; the same scope may
    # contain different immutable drafts and publication decisions.
    item_by_digest = {item.publication_digest: item for item in request.items}
    for row in sorted(rows, key=lambda r: (r.identity_key, r.draft_digest, r.digest)):
        item = item_by_digest[row.digest]
        capabilities: list[dict[str, Any]] = []
        for capability in item.capabilities:
            try:
                lookup = reviewed_policy_terms.lookup_terms if require_terms else publication.lookup
                outcome = await lookup(
                    db,
                    issuer=issuer,
                    digest=row.digest,
                    capability=capability,
                    context=item.context,
                )
            except WorkflowError as exc:
                if exc.status == 404:
                    outcome = _unavailable(capability, "not_found")
                elif exc.status == 409:
                    outcome = _unavailable(capability, "integrity_check_failed")
                else:
                    raise
            except (ValueError, KeyError):
                # Never expose source contents in error messages or partial facts.
                outcome = _unavailable(capability, "integrity_check_failed")
            capabilities.append(outcome)
        result_by_digest[row.digest] = {
            "publication_digest": row.digest,
            "scenario": item.context.model_dump(mode="json"),
            "capabilities": capabilities,
        }

    # Expiry may occur while other selected PDFs are being validated. Held row
    # locks prevent concurrent revocation/review changes until this transaction
    # ends; this last check handles time advancing within the comparison.
    for row in rows:
        state, _ = await publication._state(db, row)
        if state != "published":
            entry = result_by_digest[row.digest]
            entry["capabilities"] = [
                _unavailable(capability["capability"], state)
                for capability in entry["capabilities"]
            ]

    # Use one final timestamp across every capability, including an earlier
    # result whose approval may have expired during a later result's checks.
    checked_at = datetime.now(UTC)
    entries = []
    for item in request.items:
        selected_entry = result_by_digest.get(item.publication_digest)
        if selected_entry is None:
            selected_entry = {
                "publication_digest": item.publication_digest,
                "scenario": item.context.model_dump(mode="json"),
                "capabilities": [_unavailable(cap, "not_found") for cap in item.capabilities],
            }
        for index, capability in enumerate(selected_entry["capabilities"]):
            if capability["status"] == "available":
                expiry = datetime.fromisoformat(capability["expires_at"])
                if expiry <= checked_at:
                    selected_entry["capabilities"][index] = _unavailable(
                        capability["capability"], "expired"
                    )
        entries.append(selected_entry)
    statuses = [cap["status"] for item in entries for cap in item["capabilities"]]
    available = sum(status == "available" for status in statuses)
    status = "complete" if available == len(statuses) else "partial" if available else "unavailable"
    return {
        "status": status,
        "scope": "reviewed_graph_comparison" if require_terms else "internal_review_preview",
        "checked_at": checked_at.isoformat(),
        "requires_fresh_lookup": True,
        "customer_delivery_authorized": False,
        "items": entries,
    }
