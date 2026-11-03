"""Offline source-review packages. Validation never approves or imports policy data.

No Settings, database, network or model dependency. Values remain proposals until
authenticated review and a unit-aware database importer are implemented.
"""

from __future__ import annotations

import hashlib
import io
import json
from datetime import date
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pypdf import PdfReader

Text = Annotated[str, Field(strict=True, min_length=1, max_length=4000)]
Digest = Annotated[str, Field(strict=True, pattern=r"^[a-f0-9]{64}$")]
Positive = Annotated[int, Field(strict=True, gt=0)]
FIELDS = {
    "uin",
    "variant",
    "effective_date",
    "expiry_date",
    "sum_insured_options",
    "adult_entry_age_min",
    "adult_entry_age_max",
    "ped_waiting_period",
    "exclusions",
    "premium_table",
}


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Source(ClosedModel):
    id: Text
    url: Text
    sha256: Digest
    accessed_on: date
    page_count: Positive

    @model_validator(mode="after")
    def safe_url(self) -> Source:
        parsed = urlsplit(self.url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("A credential-free HTTPS source URL is required")
        return self


class Reference(ClosedModel):
    source_id: Text
    pdf_page: Positive  # One-based physical PDF page, not printed page numbering.
    clause: Text
    quote: Text


class ProposedField(ClosedModel):
    name: Literal[
        "uin",
        "variant",
        "effective_date",
        "expiry_date",
        "sum_insured_options",
        "adult_entry_age_min",
        "adult_entry_age_max",
        "ped_waiting_period",
        "exclusions",
        "premium_table",
    ]
    status: Literal["missing", "extracted"]
    # Text preserves source units/conditions; it is never a database-ready number.
    proposed_value: Text | None = None
    unit: Literal["text", "date", "INR", "years", "days", "calendar_months"] | None = None
    references: list[Reference] = Field(default_factory=list, max_length=20)
    conditions: list[Text] = Field(default_factory=list, max_length=30)
    unresolved: list[Text] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def honest_status(self) -> ProposedField:
        if self.status == "missing":
            if self.proposed_value is not None or self.unit is not None or self.references:
                raise ValueError("Missing fields cannot carry proposed values or references")
            if not self.unresolved:
                raise ValueError("Explain why a required field is missing")
        else:
            if self.proposed_value is None or not self.references or self.unit is None:
                raise ValueError("Extracted fields require value, unit and source references")
            allowed = {
                "ped_waiting_period": {"days", "calendar_months"},
                "sum_insured_options": {"INR"},
                "adult_entry_age_min": {"years"},
                "adult_entry_age_max": {"years"},
                "effective_date": {"date"},
                "expiry_date": {"date"},
            }.get(self.name, {"text"})
            if self.unit not in allowed:
                raise ValueError("Field unit is incompatible with its meaning")
            if self.unit == "date":
                date.fromisoformat(self.proposed_value)
        return self


class ReviewPackage(ClosedModel):
    format_version: Literal["policy-source-review-v1"]
    insurer: Text
    product: Text
    review_status: Literal["pending_human_review"]
    sources: list[Source] = Field(min_length=1, max_length=20)
    fields: list[ProposedField] = Field(min_length=10, max_length=10)

    @model_validator(mode="after")
    def linked_evidence(self) -> ReviewPackage:
        sources = {source.id: source for source in self.sources}
        if len(sources) != len(self.sources):
            raise ValueError("Duplicate source identity")
        if {field.name for field in self.fields} != FIELDS:
            raise ValueError("Every required field must appear exactly once")
        for field in self.fields:
            for ref in field.references:
                if ref.source_id not in sources:
                    raise ValueError("Unknown source reference")
                if ref.pdf_page > sources[ref.source_id].page_count:
                    raise ValueError("Reference exceeds document page count")
        dates = {f.name: f.proposed_value for f in self.fields if f.unit == "date"}
        start, end = dates.get("effective_date"), dates.get("expiry_date")
        if start and end and date.fromisoformat(end) < date.fromisoformat(start):
            raise ValueError("Expiry cannot precede effective date")
        return self


def validate_package(raw: str, source_bytes: dict[str, bytes], *, as_of: date) -> dict[str, object]:
    """Check pinned PDF bytes and package structure, never source authenticity or truth."""

    def unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON field")
            result[key] = value
        return result

    # Reject ambiguous JSON before Pydantic's normal object decoder.
    json.loads(raw, object_pairs_hook=unique_keys)
    package = ReviewPackage.model_validate_json(raw)
    if set(source_bytes) != {source.id for source in package.sources}:
        raise ValueError("Exact source byte set required")
    for source in package.sources:
        content = source_bytes[source.id]
        if source.accessed_on > as_of:
            raise ValueError("Source access date cannot be in the future")
        if not content.startswith(b"%PDF-") or len(content) > 20 * 1024 * 1024:
            raise ValueError("Expected bounded PDF source bytes")
        if hashlib.sha256(content).hexdigest() != source.sha256:
            raise ValueError("Source bytes differ from pinned hash")
        reader = PdfReader(io.BytesIO(content))
        # Public PDFs may use permission encryption with an empty read password.
        # Never accept or request a private password through this package.
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError("Source requires a private read password")
        if len(reader.pages) != source.page_count:
            raise ValueError("Source page count mismatch or encrypted document")
        page_text: dict[int, str] = {}
        for field in package.fields:
            for ref in field.references:
                if ref.source_id != source.id:
                    continue
                if ref.pdf_page not in page_text:
                    page_text[ref.pdf_page] = " ".join(
                        reader.pages[ref.pdf_page - 1].extract_text().split()
                    )
                if " ".join(ref.quote.split()) not in page_text[ref.pdf_page]:
                    raise ValueError("Quoted evidence not found on referenced PDF page")
    digest = hashlib.sha256(package.model_dump_json().encode()).hexdigest()
    return {
        "package_sha256": digest,
        "structurally_valid": True,
        "missing_fields": [f.name for f in package.fields if f.status == "missing"],
        "unresolved_fields": [f.name for f in package.fields if f.unresolved],
        "review_status": package.review_status,
        "approved_for_import": False,
        "production_approved": False,
    }
