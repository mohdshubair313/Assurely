"""Versioned, deterministic applicability and conditional fact-publication contract.

This publishes scoped facts, not quotes, claim settlements or personal eligibility.
Unsupported rule families cannot be enabled by a reviewer flag.
"""

from __future__ import annotations

import hashlib
import io
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr, model_validator
from pypdf import PdfReader

from app.db.policy_rule_draft import AgeValue, PolicyRuleDraft, TextValue
from app.db.source_review import ClosedModel, Digest, Reference, Text

Capability = Literal["coverage_options", "adult_entry_ages", "base_ped_wait"]
REQUIRED = {
    "coverage_options": {"sum_insured_options"},
    "adult_entry_ages": {"adult_entry_age_min", "adult_entry_age_max"},
    "base_ped_wait": {"ped_waiting_period"},
}


class Predicate(ClosedModel):
    field: Literal["entry_age_years", "residency", "zone", "portability", "continuity"]
    op: Literal["eq", "gte", "lte"]
    value: StrictBool | StrictInt | StrictStr

    @model_validator(mode="after")
    def typed_operand(self) -> Predicate:
        if self.field == "entry_age_years":
            if type(self.value) is not int or not 0 <= self.value <= 150:
                raise ValueError("Entry age requires an integer between zero and 150")
        else:
            expected = bool if self.field in {"portability", "continuity"} else str
            if type(self.value) is not expected or self.op != "eq":
                raise ValueError("Condition operator or value has an incompatible type")
            if isinstance(self.value, str) and (not self.value.strip() or len(self.value) > 100):
                raise ValueError("Condition text must be bounded and nonblank")
        return self

    def evaluate(self, context: dict[str, Any]) -> bool | None:
        actual = context.get(self.field)
        if type(actual) is not type(self.value):
            return None
        if self.op == "eq":
            return bool(actual == self.value)
        if self.op == "gte":
            return bool(actual >= self.value)
        return bool(actual <= self.value)


class Conditions(ClosedModel):
    # OR of bounded AND groups; [[]] is explicit unconditional, [] is invalid.
    any_of: list[Annotated[list[Predicate], Field(max_length=20)]] = Field(
        min_length=1, max_length=20
    )

    def evaluate(self, context: dict[str, Any]) -> bool | None:
        unknown = False
        for group in self.any_of:
            values = [p.evaluate(context) for p in group]
            if all(v is True for v in values):
                return True
            if not any(v is False for v in values):
                unknown = True
        return None if unknown else False


class DateWindow(ClosedModel):
    start: date
    end_kind: Literal["inclusive", "no_declared_end", "unknown"]
    end: date | None = None

    @model_validator(mode="after")
    def consistent_end(self) -> DateWindow:
        if (self.end_kind == "inclusive") != (self.end is not None):
            raise ValueError("Only an inclusive end has an end date")
        if self.end is not None and self.end < self.start:
            raise ValueError("End date precedes start date")
        return self

    def contains(self, value: date) -> bool | None:
        if self.end_kind == "unknown":
            return None
        return self.start <= value and (self.end is None or value <= self.end)


class Applicability(ClosedModel):
    # Product revision dates are deliberately not accepted as policy issue dates.
    date_basis: Literal["policy_issue_date", "policy_renewal_date"]
    window: DateWindow
    cover_basis: Literal["individual", "family_floater"]
    selected_options: list[Text] = Field(max_length=20)
    evidence: list[Reference] = Field(min_length=1, max_length=20)
    rationale: Text

    @model_validator(mode="after")
    def unique_options(self) -> Applicability:
        if len(set(self.selected_options)) != len(self.selected_options):
            raise ValueError("Duplicate selected option")
        return self


class NoteMapping(ClosedModel):
    note_sha256: Digest
    disposition: Literal["condition", "outside_capability", "resolved_by_evidence"]
    rationale: Text
    evidence: list[Reference] = Field(min_length=1, max_length=20)


class FactScope(ClosedModel):
    capability: Capability
    conditions: Conditions
    age_basis: Literal["completed_years_at_entry", "nearest_birthday_at_entry"] | None = None
    evidence: list[Reference] = Field(min_length=1, max_length=20)
    note_mappings: list[NoteMapping] = Field(max_length=120)

    @model_validator(mode="after")
    def age_scope(self) -> FactScope:
        if (self.capability == "adult_entry_ages") != (self.age_basis is not None):
            raise ValueError("Only adult age facts require an explicit age basis")
        return self


class PublicationManifest(ClosedModel):
    format_version: Literal["policy-publication-v1"] = "policy-publication-v1"
    draft_digest: Digest
    applicability: Applicability
    scopes: list[FactScope] = Field(min_length=1, max_length=3)
    identity_notes: list[NoteMapping] = Field(max_length=120)
    # Separately reviewed source authenticity/screening record, not a caller boolean.
    source_review: Text

    @model_validator(mode="after")
    def unique_scopes(self) -> PublicationManifest:
        names = [s.capability for s in self.scopes]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate capability")
        return self


class LookupContext(ClosedModel):
    transaction: Literal["issue", "renewal"]
    transaction_date: date
    cover_basis: Literal["individual", "family_floater"]
    selected_options: list[Text] = Field(max_length=20)
    entry_age_years: Annotated[int, Field(strict=True, ge=0, le=150)] | None = None
    residency: Annotated[str, Field(strict=True, min_length=1, max_length=100)] | None = None
    zone: Annotated[str, Field(strict=True, min_length=1, max_length=100)] | None = None
    portability: StrictBool | None = None
    continuity: StrictBool | None = None

    @model_validator(mode="after")
    def unique_options(self) -> LookupContext:
        if len(set(self.selected_options)) != len(self.selected_options):
            raise ValueError("Duplicate selected option")
        return self


def note_id(field: str, kind: str, index: int, text: str) -> str:
    return hashlib.sha256(f"{field}|{kind}|{index}|{text}".encode()).hexdigest()


def required_notes(draft: PolicyRuleDraft, names: set[str]) -> set[str]:
    return {
        note_id(f.name, kind, index, note)
        for f in draft.source_package.fields
        if f.name in names
        for kind in ("conditions", "unresolved")
        for index, note in enumerate(getattr(f, kind))
    }


def _check_notes(expected: set[str], mappings: list[NoteMapping], conditions: Conditions) -> None:
    ids = [m.note_sha256 for m in mappings]
    if len(ids) != len(set(ids)) or set(ids) != expected:
        raise ValueError("Every source condition and unresolved note needs an exact mapping")
    if any(m.disposition == "condition" for m in mappings) and any(
        not group for group in conditions.any_of
    ):
        raise ValueError("A conditional resolution cannot become unconditional")


def identity(draft: PolicyRuleDraft) -> tuple[str, str, str, str]:
    fields = {f.name: f for f in draft.fields}
    uin, variant = fields["uin"].value, fields["variant"].value
    if not isinstance(uin, TextValue) or not isinstance(variant, TextValue):
        raise ValueError("Exact UIN and variant are required")
    return draft.source_package.insurer, draft.source_package.product, uin.value, variant.value


def validate_manifest(manifest: PublicationManifest, draft: PolicyRuleDraft) -> None:
    identity(draft)
    if manifest.applicability.window.end_kind == "unknown":
        raise ValueError("Unknown applicability end blocks publication")
    _check_notes(
        required_notes(draft, {"uin", "variant", "effective_date", "expiry_date"}),
        manifest.identity_notes,
        Conditions(any_of=[[]]),
    )
    fields = {f.name: f for f in draft.fields}
    for scope in manifest.scopes:
        names = REQUIRED[scope.capability]
        if any(fields[n].status != "proposed" or fields[n].value is None for n in names):
            raise ValueError("Capability requires complete typed source facts")
        _check_notes(required_notes(draft, names), scope.note_mappings, scope.conditions)
        if scope.capability == "adult_entry_ages":
            lower, upper = fields["adult_entry_age_min"].value, fields["adult_entry_age_max"].value
            if not isinstance(lower, AgeValue) or not isinstance(upper, AgeValue):
                raise ValueError("Invalid age values")
            if lower.years is None or (upper.years is not None and upper.years < lower.years):
                raise ValueError("Incompatible entry age bounds")


def validate_evidence(
    manifest: PublicationManifest, draft: PolicyRuleDraft, blobs: dict[str, bytes]
) -> None:
    """Check added interpretation references against already revalidated pinned bytes."""
    refs = list(manifest.applicability.evidence)
    for mapping in manifest.identity_notes:
        refs.extend(mapping.evidence)
    for scope in manifest.scopes:
        refs.extend(scope.evidence)
        for mapping in scope.note_mappings:
            refs.extend(mapping.evidence)
    sources = {s.id: s for s in draft.source_package.sources}
    readers: dict[str, PdfReader] = {}
    pages: dict[tuple[str, int], str] = {}
    for ref in refs:
        source = sources.get(ref.source_id)
        if source is None or ref.pdf_page > source.page_count:
            raise ValueError("Unknown publication evidence reference")
        if source.id not in readers:
            content = blobs[source.sha256]
            if hashlib.sha256(content).hexdigest() != source.sha256:
                raise ValueError("Publication evidence hash mismatch")
            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted and not reader.decrypt(""):
                raise ValueError("Publication evidence requires a password")
            readers[source.id] = reader
        key = (source.id, ref.pdf_page)
        if key not in pages:
            pages[key] = " ".join(readers[source.id].pages[ref.pdf_page - 1].extract_text().split())
        if " ".join(ref.quote.split()) not in pages[key]:
            raise ValueError("Publication evidence quote is absent")


def applicability_result(manifest: PublicationManifest, context: LookupContext) -> str:
    app = manifest.applicability
    expected = "issue" if app.date_basis == "policy_issue_date" else "renewal"
    if (
        context.transaction != expected
        or context.cover_basis != app.cover_basis
        or set(context.selected_options) != set(app.selected_options)
    ):
        return "not_applicable"
    value = app.window.contains(context.transaction_date)
    return "applicable" if value is True else "unknown" if value is None else "not_applicable"
