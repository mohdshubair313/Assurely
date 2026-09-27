"""Escalation model — maps to the ``escalations`` table (LLD § 7.4).

Columns:
    id               — UUID primary key
    session_id       — FK to sessions.id
    reason           — why the case was escalated
    status           — 'pending' | 'assigned' | 'in_review' | 'resolved'
    assigned_advisor — FK to users.id (advisor role)
    created_at       — timestamp

Escalation gates delivery, not generation (AGENTS.md rule 4).
The explanation_report node still generates output for escalated
cases — the escalate node just holds it for advisor sign-off.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base


class Escalation(Base):
    __tablename__ = "escalations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="pending")
    assigned_advisor: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
