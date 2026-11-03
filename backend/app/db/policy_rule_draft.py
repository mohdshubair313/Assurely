"""Offline normalization of source proposals, never approval or a database import.

Only lossless, explicitly supported representations are converted. Conditions and
evidence remain in the embedded source package; no policy rules are executed.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from app.db.source_review import (
    ClosedModel,
    Digest,
    ProposedField,
    ReviewPackage,
    Text,
    validate_package,
)


class TextValue(ClosedModel):
    kind: Literal["text"] = "text"
    value: Text


class SourceDateValue(ClosedModel):
    kind: Literal["source_date"] = "source_date"
    value: date
    # A source-review effective_date is not sufficient to choose a live interval.
    meaning: Literal["requires_applicability_review"] = "requires_applicability_review"


class CoverOptionsValue(ClosedModel):
    kind: Literal["cover_options"] = "cover_options"
    currency: Literal["INR"] = "INR"
    unit: Literal["paise"] = "paise"
    amounts: list[Annotated[int, Field(strict=True, gt=0)]] = Field(min_length=1)
    interpolation: Literal["not_authorized"] = "not_authorized"

    @model_validator(mode="after")
    def distinct_options(self) -> CoverOptionsValue:
        if len(set(self.amounts)) != len(self.amounts):
            raise ValueError("Duplicate coverage option")
        return self


class AgeValue(ClosedModel):
    kind: Literal["age"] = "age"
    bound: Literal["finite", "unbounded"]
    years: Annotated[int, Field(strict=True, ge=0)] | None
    age_basis: Literal["requires_rule_review"] = "requires_rule_review"

    @model_validator(mode="after")
    def explicit_bound(self) -> AgeValue:
        if (self.bound == "unbounded") != (self.years is None):
            raise ValueError("Only explicit unbounded age has no numeric limit")
        return self


class PeriodValue(ClosedModel):
    kind: Literal["waiting_period"] = "waiting_period"
    count: Annotated[int, Field(strict=True, ge=0)]
    unit: Literal["days", "calendar_months"]


Value = Annotated[
    TextValue | SourceDateValue | CoverOptionsValue | AgeValue | PeriodValue,
    Field(discriminator="kind"),
]


class DraftField(ClosedModel):
    name: Text
    status: Literal["proposed", "unavailable", "needs_interpretation"]
    value: Value | None
    reason: Text


class PolicyRuleDraft(ClosedModel):
    format_version: Literal["policy-rule-draft-v1"] = "policy-rule-draft-v1"
    normalizer_version: Literal["1"] = "1"
    normalized_on: date
    source_package_sha256: Digest
    source_package: ReviewPackage
    fields: list[DraftField] = Field(min_length=10, max_length=10)
    review_status: Literal["pending_human_review"] = "pending_human_review"
    approved_for_import: Literal[False] = False
    production_approved: Literal[False] = False

    @model_validator(mode="after")
    def bound_to_proposals(self) -> PolicyRuleDraft:
        digest = hashlib.sha256(self.source_package.model_dump_json().encode()).hexdigest()
        if digest != self.source_package_sha256:
            raise ValueError("Source package digest mismatch")
        expected = [_normalize(f) for f in sorted(self.source_package.fields, key=lambda f: f.name)]
        if self.fields != expected:
            raise ValueError("Normalized fields differ from source proposals")
        if any(s.accessed_on > self.normalized_on for s in self.source_package.sources):
            raise ValueError("Normalization predates source acquisition")
        return self


def _integer(value: str) -> int:
    if not re.fullmatch(r"(?:0|[1-9][0-9]{0,8})", value):
        raise ValueError("Expected an explicit non-negative integer")
    return int(value)


def _paise(value: str) -> int:
    if not re.fullmatch(r"(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,2})?", value):
        raise ValueError("Expected explicit INR without grouping, shorthand or rounding")
    amount = int(Decimal(value) * 100)
    if amount <= 0:
        raise ValueError("Coverage must be positive")
    return amount


def _normalize(field: ProposedField) -> DraftField:
    if field.status == "missing":
        return DraftField(
            name=field.name, status="unavailable", value=None,
            reason="Source proposal is missing; never substitute zero, empty rules or infinity.",
        )
    raw = field.proposed_value
    assert raw is not None  # Enforced by the source-review contract.
    value: TextValue | SourceDateValue | CoverOptionsValue | AgeValue | PeriodValue
    try:
        if field.name in {"uin", "variant"}:
            if raw != raw.strip() or not raw.strip():
                raise ValueError("Identity text must be nonblank with no surrounding whitespace")
            value = TextValue(value=raw)
        elif field.name in {"effective_date", "expiry_date"}:
            value = SourceDateValue(value=date.fromisoformat(raw))
        elif field.name == "sum_insured_options":
            value = CoverOptionsValue(amounts=[_paise(part.strip()) for part in raw.split(";")])
        elif field.name in {"adult_entry_age_min", "adult_entry_age_max"}:
            if field.name == "adult_entry_age_max" and raw in {
                "Lifelong", "No maximum entry age limit",
            }:
                value = AgeValue(bound="unbounded", years=None)
            else:
                value = AgeValue(bound="finite", years=_integer(raw))
        elif field.name == "ped_waiting_period":
            if field.unit not in {"days", "calendar_months"}:
                raise ValueError("Unsupported waiting-period unit")
            value = PeriodValue(count=_integer(raw), unit=field.unit)
        else:
            raise ValueError(
                "Conditional exclusions and tariff matrices need a reviewed rule mapping"
            )
    except ValueError as exc:
        return DraftField(
            name=field.name, status="needs_interpretation", value=None, reason=str(exc),
        )
    return DraftField(
        name=field.name, status="proposed", value=value,
        reason=(
            "Representation only; original evidence, conditions and unresolved notes still apply."
        ),
    )


def build_draft(raw: str, source_bytes: dict[str, bytes], *, as_of: date) -> PolicyRuleDraft:
    """Revalidate actual PDFs before normalizing; no caller-supplied approval receipt."""
    receipt = validate_package(raw, source_bytes, as_of=as_of)
    package = ReviewPackage.model_validate_json(raw)
    return PolicyRuleDraft(
        normalized_on=as_of,
        source_package_sha256=str(receipt["package_sha256"]),
        source_package=package,
        fields=[_normalize(f) for f in sorted(package.fields, key=lambda f: f.name)],
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def assess_draft(raw: str, source_bytes: dict[str, bytes], *, as_of: date) -> dict[str, Any]:
    """Validate an untrusted draft and return a blocked, digest-bound import preview.

    The future authenticated approval/import service must be implemented separately.
    This function cannot issue a permission to import, even for a complete proposal.
    """
    json.loads(raw, object_pairs_hook=_unique_object)
    draft = PolicyRuleDraft.model_validate_json(raw)
    if draft.normalized_on > as_of:
        raise ValueError("Normalization date cannot be in the future")
    validate_package(draft.source_package.model_dump_json(), source_bytes, as_of=as_of)
    blockers: list[dict[str, Any]] = [
        {"code": "authenticated_review_required", "field": None},
        {"code": "applicability_mapping_required", "field": None},
        {"code": "normalized_persistence_not_implemented", "field": None},
        {"code": "conditional_rule_mapping_required", "field": None},
    ]
    originals: dict[str, ProposedField] = {f.name: f for f in draft.source_package.fields}
    for field in draft.fields:
        original = originals[field.name]
        if field.status != "proposed":
            blockers.append({"code": field.status, "field": field.name, "detail": field.reason})
        if original.unresolved:
            blockers.append({
                "code": "unresolved_source_review", "field": field.name,
                "details": original.unresolved,
            })
        if original.conditions:
            blockers.append({
                "code": "conditions_require_mapping", "field": field.name,
                "details": original.conditions,
            })
    ages = {f.name: f.value for f in draft.fields if isinstance(f.value, AgeValue)}
    minimum, maximum = ages.get("adult_entry_age_min"), ages.get("adult_entry_age_max")
    if (
        minimum and maximum and minimum.years is not None and maximum.years is not None
        and minimum.years > maximum.years
    ):
        blockers.append({"code": "conflicting_age_bounds", "field": "adult_entry_age_max"})
    return {
        "draft_sha256": hashlib.sha256(draft.model_dump_json().encode()).hexdigest(),
        "source_package_sha256": draft.source_package_sha256,
        "checked_on": as_of.isoformat(),
        "proposed_fields": [f.name for f in draft.fields if f.status == "proposed"],
        "unavailable_fields": [f.name for f in draft.fields if f.status == "unavailable"],
        "interpretation_required": [
            f.name for f in draft.fields if f.status == "needs_interpretation"
        ],
        "blockers": blockers,
        "approved_for_import": False,
        "production_approved": False,
    }
