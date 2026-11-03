"""PolicyTerms model — maps to the ``policy_terms`` table (LLD § 7.4).

Columns:
    id                              — UUID primary key
    policy_document_id              — FK to policy_documents.id
    version_hash                    — version of these specific terms
    sum_insured_min / sum_insured_max — coverage range
    entry_age_min / entry_age_max   — age eligibility window
    waiting_period_days_preexisting — days before pre-existing conditions covered
    exclusions_json                 — JSONB list of exclusions
    premium_rate_table_json         — JSONB rate table for deterministic premium lookup
    effective_date / expiry_date    — legacy stored validity only
    record_kind                     — legacy or reviewed_v1
    publication_digest              — exact reviewed publication, if imported
    reviewed_facts_json             — unit-preserving reviewed values, if imported

Reviewed rows deliberately have null legacy fields; their issue/renewal scope is
validated against the publication manifest on every read.

CRITICAL (AGENTS.md rule 5):
    This table is queried DETERMINISTICALLY — never by an LLM.
    Eligibility, exclusions, sum-insured limits, premium figures,
    and effective dates all come from structured lookups against
    this table. RAG is reserved for clause wording and explanations only.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base


class PolicyTerms(Base):
    __tablename__ = "policy_terms"
    __table_args__ = (
        CheckConstraint(
            "(record_kind = 'legacy' AND policy_document_id IS NOT NULL "
            "AND effective_date IS NOT NULL AND publication_digest IS NULL "
            "AND reviewed_facts_json IS NULL) OR "
            "(record_kind = 'reviewed_v1' AND policy_document_id IS NULL "
            "AND effective_date IS NULL AND expiry_date IS NULL AND publication_digest IS NOT NULL "
            "AND version_hash = publication_digest AND reviewed_facts_json IS NOT NULL "
            "AND sum_insured_min IS NULL AND sum_insured_max IS NULL "
            "AND entry_age_min IS NULL AND entry_age_max IS NULL "
            "AND waiting_period_days_preexisting IS NULL AND exclusions_json IS NULL "
            "AND premium_rate_table_json IS NULL)",
            name="ck_policy_terms_record_kind",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    policy_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policy_documents.id", ondelete="CASCADE"), nullable=True
    )
    version_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sum_insured_min: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=15, scale=2), nullable=True
    )
    sum_insured_max: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=15, scale=2), nullable=True
    )
    entry_age_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    entry_age_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    waiting_period_days_preexisting: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exclusions_json: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    premium_rate_table_json: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Reviewed v1 uses its own exact typed fields; legacy projections remain null.
    record_kind: Mapped[str] = mapped_column(String(20), nullable=False, server_default="legacy")
    publication_digest: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("policy_publications.digest", ondelete="RESTRICT"), unique=True
    )
    reviewed_facts_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
