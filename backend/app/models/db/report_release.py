"""Current turn binding and immutable evidence of a release decision."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base


class ReportHead(Base):
    __tablename__ = "report_heads"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'complete', 'failed')", name="ck_report_head_status"
        ),
        CheckConstraint(
            "status = 'complete' OR (report_digest IS NULL AND NOT guardrail_approved)",
            name="ck_report_head_pending",
        ),
    )
    issuer: Mapped[str] = mapped_column(String(500), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    turn_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    report_digest: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("advisor_reports.digest", ondelete="RESTRICT"),
        nullable=True,
    )
    guardrail_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ReleaseReceipt(Base):
    __tablename__ = "report_release_receipts"
    __table_args__ = (
        UniqueConstraint("issuer", "owner_id", "request_key", name="uq_release_request"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    issuer: Mapped[str] = mapped_column(String(500), nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    turn_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    report_digest: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("advisor_reports.digest", ondelete="RESTRICT"),
        nullable=False,
    )
    advisor_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("advisor_decisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    request_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
