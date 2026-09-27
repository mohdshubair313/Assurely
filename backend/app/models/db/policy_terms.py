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
    effective_date                  — when these terms become active
    expiry_date                     — when these terms expire (nullable)

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

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base


class PolicyTerms(Base):
    __tablename__ = "policy_terms"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    policy_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policy_documents.id", ondelete="CASCADE"), nullable=False
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
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
