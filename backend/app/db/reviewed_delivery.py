"""Request-local revalidation of reviewed reports; never a reusable release token."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.reviewed_comparison import ComparisonRequest, compare_terms
from app.graph.nodes.guardrail import check_ranking_language, check_unlicensed_advice
from app.graph.reviewed_report import reviewed_evidence
from app.graph.state import SessionState


@dataclass(frozen=True)
class DeliveryCheck:
    """Evidence consistency is separate from advisor authorization."""

    evidence_current: bool
    reason: str


def is_reviewed(state: dict[str, Any]) -> bool:
    draft = state.get("draft_output") or {}
    report = state.get("output") or {}
    return bool(
        "reviewed_comparison" in draft or "reviewed_report" in report
        or state.get("reviewed_comparison_request") is not None
        or draft.get("publication_gate") == "blocked"
    )


def _stable(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Only lookup time is volatile. Expiry, event IDs, source hashes, exact values
    # and scope must still match. Never normalize numbers or discard conditions.
    return [{k: v for k, v in item.items() if k != "checked_at"} for item in evidence]


def _same(left: Any, right: Any) -> bool:
    # Python equality conflates bool/int and integer/float values. The report
    # contract requires exact JSON types as well as values.
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(
        right, sort_keys=True, allow_nan=False,
    )


async def check_reviewed_delivery(
    db: AsyncSession, issuer: str, state: dict[str, Any],
) -> DeliveryCheck:
    """Check within the caller's transaction and current publication namespace.

    compare_terms locks publication identities/drafts and revalidates source bytes,
    representation approval, current publication event, expiry, applicability,
    predicates and the immutable policy_terms snapshot. Nothing is written into
    graph output, and no approval flag or queue acknowledgement is consulted.
    """
    if not issuer.strip():
        return DeliveryCheck(False, "issuer_unconfigured")
    # Isolate the exact in-flight snapshot from mutable checkpoint dictionaries.
    snapshot = cast(SessionState, copy.deepcopy(state))
    try:
        original, unavailable = reviewed_evidence(snapshot)
        report = snapshot["output"]
        metadata = report["reviewed_report"]
        if (
            not original or unavailable
            or len(original) > 32 or any(len(item["claim"]) > 4096 for item in original)
            or set(report) != {"reply", "sentences", "target_language", "evidence_count",
                               "report_status", "claim_support", "reviewed_report"}
            or report.get("report_status") != "reviewed_report_held"
            or metadata != {
                "adapter_version": "reviewed-terms-v1",
                "customer_delivery_authorized": False,
                "requires_fresh_lookup": True,
                "unavailable_capabilities": [],
            }
            or report.get("target_language") != "en"
            or report.get("evidence_count") != len(original)
            or report.get("claim_support", {}).get("supported") is not True
        ):
            return DeliveryCheck(False, "report_incomplete_or_invalid")
        expected = [{"text": item["claim"], "citations": [item]} for item in original]
        reply = " ".join(
            f"{item['claim']} [Source: {item['source']}; last verified: {item['last_verified']}]"
            for item in original
        )
        if not _same(report.get("sentences"), expected) or report.get("reply") != reply:
            return DeliveryCheck(False, "report_content_changed")
        if any(check_ranking_language(item["claim"]) or check_unlicensed_advice(item["claim"])
               for item in original):
            return DeliveryCheck(False, "report_compliance_failed")
        request = ComparisonRequest.model_validate_json(
            json.dumps(snapshot["reviewed_comparison_request"])
        )
        fresh = await compare_terms(db, issuer, request)
        snapshot["draft_output"] = {**snapshot["draft_output"], "reviewed_comparison": fresh}
        current, missing = reviewed_evidence(snapshot)
        if missing or not _same(_stable(original), _stable(current)):
            return DeliveryCheck(False, "publication_or_evidence_changed")
        return DeliveryCheck(True, "advisor_authorization_required")
    except (ValueError, TypeError, KeyError, AttributeError):
        return DeliveryCheck(False, "invalid_or_expired_evidence")
