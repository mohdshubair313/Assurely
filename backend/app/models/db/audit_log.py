"""AuditLog model — maps to the ``audit_log`` table (LLD § 7.4).

Columns:
    id            — UUID primary key
    session_id    — FK to sessions.id
    node_name     — which graph node produced this entry
    input_hash    — SHA-256 of the node's input (for replay verification)
    output_hash   — SHA-256 of the node's output
    sources_json  — JSONB list of sources consulted
    created_at    — timestamp

The audit log is the technical backbone of the replayable audit trail.
Every graph node execution writes one row. Combined with decision_trace,
it answers "what happened, in what order, using what data" for any session.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    node_name: Mapped[str] = mapped_column(String(50), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sources_json: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
