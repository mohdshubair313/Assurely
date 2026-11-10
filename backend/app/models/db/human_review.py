"""Immutable customer requests; no request can grant advisor authority."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base


class HumanReviewRequest(Base):
    __tablename__ = "human_review_requests"
    __table_args__ = (
        UniqueConstraint("issuer", "owner_id", "request_key", name="uq_human_review_request"),
        CheckConstraint("request_digest ~ '^[a-f0-9]{64}$'", name="ck_human_review_digest"),
        CheckConstraint("length(btrim(issuer)) > 0", name="ck_human_review_issuer"),
        Index("ix_human_review_case", "issuer", "session_id", "requested_at"),
        Index("ix_human_review_owner", "issuer", "owner_id", "requested_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    issuer: Mapped[str] = mapped_column(String(500), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    request_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    escalation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("escalations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )
