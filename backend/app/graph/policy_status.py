"""Deterministic validity of stored policy records, never personal cover status.

Effective and expiry dates are inclusive calendar dates in UTC. Evidence below
verifies a database lookup only; it does not certify the insurer's source or
establish withdrawal of a product. No requested date is used as a fact.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.graph.nodes.health_domain_agent import _latest_user_request
from app.models.db.policy_document import PolicyDocument
from app.models.db.policy_terms import PolicyTerms

_STATUS_QUERY = re.compile(
    r"\b(?:active|expired?|expiry|validity|valid|inactive|discontinued|withdrawn|status)\b",
    re.IGNORECASE,
)
_KIND = "policy_record_status"
_SCOPE = (
    "This checks stored record validity only, not personal insurance cover or insurer "
    "product withdrawal. The verification date is the database lookup date, not "
    "verification of the insurer source. Other benefit questions require separate evidence."
)


def policy_status_request(messages: list[dict[str, Any]]) -> str | None:
    """Keep status scope through intake, while respecting newer explicit questions."""
    latest_request = _latest_user_request(messages)
    for message in reversed(messages):
        content = message.get("content")
        if message.get("role") != "user" or not isinstance(content, str):
            continue
        if _STATUS_QUERY.search(content):
            return content
        if content.strip() == latest_request:
            return None
    return None


def term_status(terms: PolicyTerms, as_of: date) -> str:
    """Classify the inclusive stored interval; malformed intervals fail closed."""
    effective, expiry = terms.effective_date, terms.expiry_date
    if type(effective) is not date or (expiry is not None and type(expiry) is not date):
        return "invalid"
    if expiry is not None and expiry < effective:
        return "invalid"
    if effective > as_of:
        return "future"
    if expiry is not None and expiry < as_of:
        return "expired"
    return "active"


def _normalize(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold()))


def _matches(
    request: str, rows: list[tuple[PolicyTerms, PolicyDocument]]
) -> list[tuple[PolicyTerms, PolicyDocument]]:
    normalized = _normalize(request)
    matches: list[tuple[int, int, PolicyTerms, PolicyDocument]] = []
    for terms, doc in rows:
        if not isinstance(doc.product_name, str) or not doc.product_name.strip():
            continue
        name = _normalize(doc.product_name)
        for match in re.finditer(rf"(?<!\w){re.escape(name)}(?!\w)", normalized):
            # A requested edition cannot silently fall back to a base product.
            suffix = normalized[match.end():]
            if re.match(r"\s+(?:(?:version|edition|v)\s*)?\d{4}\b", suffix):
                continue
            version = re.match(r"\s+(?:version|edition|v)\s+(\w+)\b", suffix)
            if version and version.group(1) not in (terms.version_hash, doc.version_hash):
                continue
            matches.append((match.start(), match.end(), terms, doc))
    matches = [
        item for item in matches
        if not any(a <= item[0] and item[1] <= b and b - a > item[1] - item[0]
                   for a, b, _, _ in matches)
    ]
    # When a complete insurer name is explicitly supplied, preserve that scope.
    named_insurers = {
        doc.insurer for _, _, _, doc in matches
        if isinstance(doc.insurer, str)
        and re.search(rf"(?<!\w){re.escape(_normalize(doc.insurer))}(?!\w)", normalized)
    }
    selected: list[tuple[PolicyTerms, PolicyDocument]] = []
    seen = set()
    for _, _, terms, doc in matches:
        if named_insurers and doc.insurer not in named_insurers:
            continue
        key = (str(terms.id), str(doc.id))
        if key not in seen:
            selected.append((terms, doc))
            seen.add(key)
    return selected


def build_policy_status_facts(
    request: str | None,
    rows: list[tuple[PolicyTerms, PolicyDocument]],
    as_of: date,
) -> list[dict[str, Any]]:
    """Resolve complete known names only, returning database-scoped evidence.

    Multiple versions/insurers remain explicit; no newest-row guess is made.
    Unknown names or editions do not acquire expiry dates from user assertions.
    """
    if not request or not _STATUS_QUERY.search(request):
        return []
    matches = _matches(request, rows)
    common = {"kind": _KIND, "as_of": as_of.isoformat(),
              "last_verified": as_of.isoformat(), "verification_scope": "database_record_lookup"}
    if not matches:
        return [{**common, "status": "unknown",
                 "source": "policy_terms and policy_documents database catalog lookup",
                 "claim": (
                     f"As of {as_of.isoformat()}, no exact product/edition match was resolved "
                     "in the stored policy catalog for this status request. Its validity "
                     "cannot be verified from this lookup; absence is not evidence of expiry. "
                     + _SCOPE
                 )}]
    facts = []
    ambiguous = len(matches) > 1
    for terms, doc in matches:
        status = term_status(terms, as_of)
        label = f"{doc.insurer} — {doc.product_name}"
        effective = terms.effective_date.isoformat() if type(terms.effective_date) is date else None
        expiry = terms.expiry_date.isoformat() if type(terms.expiry_date) is date else None
        if status == "expired":
            detail = (
                f"The stored terms record's inclusive validity ended on {expiry}; "
                "it is excluded from active comparison."
            )
        elif status == "future":
            detail = (
                f"The stored terms record is not yet effective ({effective}) "
                "and is excluded from active comparison."
            )
        elif status == "invalid":
            detail = (
                "The stored terms record has an invalid date interval and is excluded "
                "from active comparison."
            )
        else:
            detail = "The stored terms record falls within its recorded validity interval."
        ambiguity = (
            "Multiple matching records were found; no unique version has been selected. "
            if ambiguous else ""
        )
        source = (
            f"policy_terms record {terms.id} (version {terms.version_hash}); "
            f"policy_documents record {doc.id} (version {doc.version_hash}); database lookup only"
        )
        facts.append({
            **common, "status": status, "ambiguous": ambiguous,
            "insurer": doc.insurer, "product_name": doc.product_name,
            "policy_document_id": str(doc.id), "policy_terms_id": str(terms.id),
            "version_hash": str(terms.version_hash), "document_version_hash": str(doc.version_hash),
            "effective_date": effective, "expiry_date": expiry,
            "source": source, "url": doc.doc_url if isinstance(doc.doc_url, str) else "",
            "claim": (
                f"{ambiguity}As of {as_of.isoformat()}, {label}: {detail} "
                f"Recorded effective date: {effective or 'invalid'}; recorded expiry date: "
                f"{expiry or 'none recorded'}. Effective and expiry dates are inclusive. " + _SCOPE
            ),
        })
    return facts
