"""Detect disagreements among concurrent structured terms for one document."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from app.graph.policy_status import term_status
from app.models.db.policy_document import PolicyDocument
from app.models.db.policy_terms import PolicyTerms

_NUMERIC_FIELDS = (
    "sum_insured_min", "sum_insured_max", "entry_age_min", "entry_age_max",
    "waiting_period_days_preexisting",
)


def _number(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    try:
        number = Decimal(str(value))
        return format(number.normalize(), "f") if number.is_finite() else None
    except InvalidOperation:
        return None


def _fields(terms: PolicyTerms) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key in _NUMERIC_FIELDS:
        value = _number(getattr(terms, key, None))
        if value is not None:
            fields[key] = value
    exclusions = terms.exclusions_json
    if isinstance(exclusions, list) and all(isinstance(item, str) for item in exclusions):
        fields["exclusions_json"] = sorted({" ".join(item.casefold().split())
                                            for item in exclusions})
    rates = terms.premium_rate_table_json
    if isinstance(rates, dict):
        for bracket, ages in rates.items():
            if not isinstance(bracket, str) or not isinstance(ages, dict):
                continue
            for age, amount in ages.items():
                value = _number(amount)
                if isinstance(age, str) and value is not None:
                    # Quoted segments distinguish keys containing punctuation.
                    fields[f"premium_rate_table_json[{bracket!r}][{age!r}]"] = value
    return fields


def detect_structured_conflicts(
    rows: list[tuple[PolicyTerms, PolicyDocument]], as_of: date,
) -> list[dict[str, Any]]:
    """Compare explicit values only; absence is not evidence of disagreement.

    Active-window filtering prevents an ordinary historical revision from being
    treated as an unresolved current conflict. Identity is the document UUID,
    never product-name similarity or a number extracted from retrieved prose.
    """
    groups: dict[str, list[tuple[PolicyTerms, PolicyDocument]]] = defaultdict(list)
    for terms, doc in rows:
        if term_status(terms, as_of) == "active":
            groups[str(doc.id)].append((terms, doc))
    conflicts: list[dict[str, Any]] = []
    for document_id, records in sorted(groups.items()):
        if len(records) < 2:
            continue
        by_field: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for terms, doc in sorted(records, key=lambda row: str(row[0].id)):
            for field, value in _fields(terms).items():
                by_field[field].append({
                    "value": value,
                    "policy_terms_id": str(terms.id),
                    "terms_version_hash": str(terms.version_hash),
                    "document_version_hash": str(doc.version_hash),
                    "effective_date": terms.effective_date.isoformat(),
                    "expiry_date": terms.expiry_date.isoformat() if terms.expiry_date else None,
                    "source": f"policy_terms record {terms.id}",
                    "url": doc.doc_url or "",
                    "last_verified": as_of.isoformat(),
                    "verification_scope": "database_record_lookup",
                })
        for field, evidence in sorted(by_field.items()):
            if len(evidence) < 2 or all(item["value"] == evidence[0]["value"]
                                        for item in evidence[1:]):
                continue
            conflicts.append({
                "kind": "structured_terms_conflict",
                "policy_document_id": document_id,
                "field": field,
                "evidence": evidence,
                "claim": (
                    f"Concurrent active database records for document {document_id} "
                    f"disagree on {field}. Advisor review is required. "
                    "This is a database consistency check, not insurer-source verification."
                ),
                "source": f"policy_terms consistency lookup for document {document_id}",
                "last_verified": as_of.isoformat(),
                "verification_scope": "database_record_lookup",
                "conflict": True,
            })
    return conflicts
