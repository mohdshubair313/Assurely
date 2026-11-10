"""Immutable case/report selection; a binding is never future release authority."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base


class VoiceCaseBinding(Base):
    __tablename__ = "voice_case_bindings"
    __table_args__ = (
        UniqueConstraint("voice_session_id", name="uq_voice_case_session"),
        UniqueConstraint("issuer", "owner_id", "request_key", name="uq_voice_case_request"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    voice_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voice_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    issuer: Mapped[str] = mapped_column(String(500), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="RESTRICT"), nullable=False
    )
    turn_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    report_digest: Mapped[str] = mapped_column(
        String(64), ForeignKey("advisor_reports.digest", ondelete="RESTRICT"), nullable=False
    )
    request_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    release_request_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    release_receipt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("report_release_receipts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    advisor_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("advisor_decisions.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()"), nullable=False
    )
