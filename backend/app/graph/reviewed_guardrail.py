"""Validate scoped evidence for guardrail approval, without granting delivery."""

from __future__ import annotations

import copy
import json
from typing import Any

from app.db.reviewed_comparison import ComparisonRequest, compare_terms
from app.db.session import AsyncSessionLocal
from app.graph.reviewed_report import reviewed_evidence
from app.graph.state import SessionState


def _stable(comparison: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(comparison)
    result.pop("checked_at", None)
    for item in result["items"]:
        for capability in item["capabilities"]:
            capability.pop("checked_at", None)
    return result


async def validate_reviewed_draft(state: SessionState, issuer: str) -> list[dict[str, Any]]:
    """Re-read every selected capability under the publication service's locks.

    Approval covers only the exact deterministic adapter's scoped claims. Neither
    a legacy draft nor a partial reviewed result can inherit this approval.
    Exceptions are sanitized by the calling node; no failure grants approval.
    """
    snapshot = copy.deepcopy(state)
    draft = snapshot["draft_output"]
    allowed = {"stage", "publication_gate", "publication_gate_reason", "need_fit_view",
               "cited_facts", "evidence_conflicts", "total_policies_evaluated",
               "reviewed_comparison"}
    if (
        not issuer.strip() or snapshot.get("input_status") != "accepted"
        or set(draft) - allowed or draft.get("publication_gate") != "blocked"
        or draft.get("need_fit_view") or draft.get("cited_facts")
        or draft.get("evidence_conflicts") or draft.get("total_policies_evaluated", 0) != 0
        or snapshot.get("hidden_clauses")
        or draft["reviewed_comparison"].get("status") != "complete"
    ):
        raise ValueError("Scoped reviewed draft is required")
    original, missing = reviewed_evidence(snapshot)
    if (missing or not original or len(original) > 32
            or any(len(item["claim"]) > 4096 for item in original)):
        raise ValueError("Complete bounded reviewed evidence is required")
    request = ComparisonRequest.model_validate_json(
        json.dumps(snapshot["reviewed_comparison_request"], allow_nan=False)
    )
    async with AsyncSessionLocal() as db, db.begin():
        fresh = await compare_terms(db, issuer, request)
        snapshot["draft_output"] = {**draft, "reviewed_comparison": fresh}
        current, missing = reviewed_evidence(snapshot)
        if missing or not current or fresh.get("status") != "complete":
            raise ValueError("Current reviewed evidence is unavailable")
        # Exact JSON equality preserves bool/integer/float distinctions. Only
        # lookup timestamps may change; expiry, scope, source and reviews may not.
        if json.dumps(_stable(draft["reviewed_comparison"]), sort_keys=True,
                      allow_nan=False) != json.dumps(_stable(fresh), sort_keys=True,
                                                     allow_nan=False):
            raise ValueError("Reviewed evidence changed")
    return original
