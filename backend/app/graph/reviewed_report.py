"""Deterministic, scoped report evidence from imported reviewed policy terms.

This adapter validates a lookup snapshot, not current publication authority.
Only the explanation_report node may use it to write output; release stays held.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from app.db.policy_publication_contract import (
    REQUIRED,
    Applicability,
    Conditions,
    LookupContext,
    NoteMapping,
)
from app.db.policy_rule_draft import AgeValue, CoverOptionsValue, PeriodValue
from app.db.reviewed_comparison import ComparisonRequest
from app.db.source_review import Reference
from app.graph.state import SessionState


def _require(condition: Any) -> None:
    if not condition:
        raise ValueError("Invalid reviewed report evidence")


def _timestamp(value: Any) -> datetime:
    _require(isinstance(value, str))
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _require(result.tzinfo is not None)
    return result


def _refs(value: Any) -> list[dict[str, Any]]:
    _require(isinstance(value, list) and 0 < len(value) <= 20)
    result = []
    for ref in value:
        _require(isinstance(ref, dict))
        parsed = Reference.model_validate({k: ref[k] for k in (
            "source_id", "pdf_page", "clause", "quote",
        )})
        url = urlsplit(ref["url"])
        _require(url.scheme == "https" and url.hostname and not url.username and not url.password)
        _require(isinstance(ref["sha256"], str) and re.fullmatch(r"[a-f0-9]{64}", ref["sha256"]))
        result.append({**parsed.model_dump(), "url": ref["url"], "sha256": ref["sha256"]})
    return result


def _value_text(name: str, raw: dict[str, Any]) -> str:
    if name == "sum_insured_options":
        covers = CoverOptionsValue.model_validate(raw)
        # Integer division preserves paise exactly; no float, rounding or ranges.
        amounts = ", ".join(f"INR {v // 100}.{v % 100:02d}" for v in covers.amounts)
        return f"Discrete sum-insured options: {amounts}; interpolation is not authorized"
    if name == "ped_waiting_period":
        period = PeriodValue.model_validate(raw)
        unit = "calendar months" if period.unit == "calendar_months" else "days"
        return f"Base pre-existing-condition waiting period: {period.count} {unit}"
    _require(name in {"adult_entry_age_min", "adult_entry_age_max"})
    basis = raw.get("age_basis")
    _require(basis in {"completed_years_at_entry", "nearest_birthday_at_entry"})
    age = AgeValue.model_validate({**raw, "age_basis": "requires_rule_review"})
    _require(name != "adult_entry_age_min" or age.bound == "finite")
    label = "Minimum" if name.endswith("min") else "Maximum"
    amount = "no declared upper limit" if age.bound == "unbounded" else f"{age.years} years"
    return f"{label} adult entry age: {amount}; age basis: {str(basis).replace('_', ' ')}"


def _mappings(value: Any) -> list[dict[str, Any]]:
    _require(isinstance(value, list) and len(value) <= 120)
    result = []
    for mapping in value:
        refs = _refs(mapping["evidence"])
        plain = [{k: r[k] for k in Reference.model_fields} for r in refs]
        parsed = NoteMapping.model_validate({**mapping, "evidence": plain})
        result.append({**parsed.model_dump(), "evidence": refs})
    _require(len({m["note_sha256"] for m in result}) == len(result))
    return result


def _scope_text(app: Applicability, conditions: Conditions) -> str:
    end = (f"through {app.window.end.isoformat()} inclusive" if app.window.end
           else "with no declared end date")
    options = json.dumps(app.selected_options, ensure_ascii=False)
    groups = []
    for group in conditions.any_of:
        groups.append("(" + " AND ".join(
            f"{p.field.replace('_', ' ')} { {'eq': '=', 'gte': '>=', 'lte': '<='}[p.op]} "
            f"{json.dumps(p.value, ensure_ascii=False)}" for p in group
        ) + ")")
    rule = ("no additional predicate" if any(not g for g in conditions.any_of)
            else " OR ".join(groups))
    return (
        f"Scope: {app.date_basis.replace('_', ' ')} from {app.window.start.isoformat()} {end}; "
        f"cover basis: {app.cover_basis.replace('_', ' ')}; selected options exactly {options}; "
        f"condition: {rule}"
    )


def reviewed_evidence(state: SessionState) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Validate snapshot shape, request binding and scope before rendering facts.

    Do not use a legacy/RAG fallback for incomplete reviewed evidence. Unknown
    capability outcomes are operational metadata, never sourced policy claims.
    """
    _require(state.get("input_status") != "rejected" and not state.get("missing_fields"))
    _require(state.get("intent") == "health")
    draft = state["draft_output"]
    _require(draft.get("stage") == "compare_verify")
    comparison = draft["reviewed_comparison"]
    _require(comparison["scope"] == "reviewed_graph_comparison")
    _require(comparison["customer_delivery_authorized"] is False)
    _require(comparison["requires_fresh_lookup"] is True)
    checked = _timestamp(comparison["checked_at"])
    now = datetime.now(UTC)
    _require(checked <= now)
    request = ComparisonRequest.model_validate_json(
        json.dumps(state["reviewed_comparison_request"])
    )
    items = comparison["items"]
    _require(isinstance(items, list) and len(items) == len(request.items))
    evidence: list[dict[str, Any]] = []
    unavailable: list[dict[str, str]] = []
    for item, selected in zip(items, request.items, strict=True):
        digest = selected.publication_digest
        _require(item["publication_digest"] == digest)
        context = LookupContext.model_validate_json(json.dumps(item["scenario"]))
        _require(context == selected.context)
        caps = item["capabilities"]
        _require(isinstance(caps, list) and len(caps) == len(selected.capabilities))
        for cap, capability in zip(caps, selected.capabilities, strict=True):
            _require(cap["capability"] == capability)
            if cap["status"] == "unavailable":
                _require(not cap.get("facts"))
                reason = cap.get("reason")
                _require(isinstance(reason, str) and re.fullmatch(r"[a-z_]{1,80}", reason))
                unavailable.append({"publication_digest": digest, "capability": capability,
                                    "reason": reason})
                continue
            _require(cap["status"] == "available" and cap["publication_digest"] == digest)
            _require(cap["storage_scope"] == "reviewed_policy_terms")
            _require(cap["verification_scope"] == "human_reviewed_conditional_product_facts")
            _require(_timestamp(cap["expires_at"]) > now)
            terms_id = str(UUID(cap["policy_terms_id"]))
            scope = cap["scope_review"]
            event_id = str(UUID(scope["verification_event_id"]))
            verified = date.fromisoformat(scope["last_verified"])
            _require(verified <= checked.date())
            app = Applicability.model_validate_json(json.dumps(cap["applicability"]))
            conditions = Conditions.model_validate_json(json.dumps(cap["conditions"]))
            _require(app.window.contains(context.transaction_date) is True)
            _require(context.transaction == (
                "issue" if app.date_basis == "policy_issue_date" else "renewal"
            ))
            _require(context.cover_basis == app.cover_basis)
            _require(set(context.selected_options) == set(app.selected_options))
            _require(conditions.evaluate(context.model_dump()) is True)
            app_refs = _refs(scope["applicability_evidence"])
            condition_refs = _refs(scope["condition_evidence"])
            identity_notes = _mappings(scope["identity_note_mappings"])
            condition_notes = _mappings(scope["condition_note_mappings"])
            _require([Reference.model_validate({k: r[k] for k in Reference.model_fields})
                      for r in app_refs] == app.evidence)
            identity = cap["identity"]
            _require(isinstance(identity, list) and len(identity) == 4
                     and all(isinstance(v, str) and v.strip() for v in identity))
            label = f"{identity[0]} / {identity[1]} (UIN {identity[2]}, variant {identity[3]})"
            facts = cap["facts"]
            _require(isinstance(facts, list) and len(facts) == len(REQUIRED[capability]))
            _require({f["name"] for f in facts} == REQUIRED[capability])
            if capability == "adult_entry_ages":
                values = {f["name"]: f["value"] for f in facts}
                lower, upper = values["adult_entry_age_min"], values["adult_entry_age_max"]
                _require(lower["age_basis"] == upper["age_basis"])
                _require(upper["years"] is None or upper["years"] >= lower["years"])
            for fact in facts:
                _require(fact["policy_terms_id"] == terms_id)
                _require(fact["verification_event_id"] == event_id)
                _require(fact["last_verified"] == scope["last_verified"])
                refs = _refs(fact["source"])
                claim = (f"{label}: {_value_text(fact['name'], fact['value'])}. "
                         f"{_scope_text(app, conditions)}. "
                         "This scoped field does not establish personal eligibility "
                         "or claim payment.")
                evidence.append({
                    "id": f"R{len(evidence) + 1}", "claim": claim, "kind": "policy_terms",
                    "source": f"policy_terms {terms_id}; publication {digest}",
                    "last_verified": scope["last_verified"], "url": refs[0]["url"],
                    "publication_digest": digest, "policy_terms_id": terms_id,
                    "verification_event_id": event_id, "capability": capability,
                    "fact_name": fact["name"], "value": fact["value"],
                    "references": refs, "applicability_evidence": app_refs,
                    "condition_evidence": condition_refs, "checked_at": comparison["checked_at"],
                    "identity_note_mappings": identity_notes,
                    "condition_note_mappings": condition_notes,
                    "expires_at": cap["expires_at"],
                })
    return evidence, unavailable
