"""DecisionTrace model — maps to the ``decision_trace`` table (LLD § 7.4).

Columns:
    id                              — UUID primary key
    session_id                      — FK to sessions.id
    user_profile_snapshot_json      — JSONB snapshot of the user profile at decision time
    policy_versions_evaluated_json  — JSONB list of {policy_id, version_hash}
    clauses_retrieved_json          — JSONB list of {policy_id, clause, score}
    rules_engine_output_json        — JSONB output from deterministic rules checks
    sources_per_claim_json          — JSONB mapping of claim → {source, last_verified}
    model_version                   — which LLM model was used
    prompt_version                  — which prompt version was used
    confidence_score                — float (0–1)
    confidence_inputs_json          — JSONB {retrieval_agreement, self_consistency}
    created_at                      — timestamp

One row per recommendation. Answers "why did it say that" without
reconstructing from logs. Supports replay-and-diff for regression
detection (eval harness § 6).

Written by persist_memory REGARDLESS of user consent — this is
operational/compliance data, not personal preference data.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import String, Float, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base


class DecisionTrace(Base):
    __tablename__ = "decision_trace"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    user_profile_snapshot_json: Mapped[Any] = mapped_column(JSONB, nullable=False)
    policy_versions_evaluated_json: Mapped[Any] = mapped_column(JSONB, nullable=False)
    clauses_retrieved_json: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    rules_engine_output_json: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    sources_per_claim_json: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_inputs_json: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
