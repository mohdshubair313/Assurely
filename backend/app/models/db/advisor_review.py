"""Immutable report snapshots and report-bound advisor decisions."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base


class AdvisorReport(Base):
    __tablename__ = "advisor_reports"

    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    issuer: Mapped[str] = mapped_column(String(500), nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )


class AdvisorDecision(Base):
    __tablename__ = "advisor_decisions"
    __table_args__ = (
        UniqueConstraint("report_digest", "revision", name="uq_advisor_revision"),
        UniqueConstraint("issuer", "actor_id", "request_key", name="uq_advisor_request"),
        CheckConstraint("revision > 0", name="ck_advisor_revision"),
        CheckConstraint(
            "(action = 'approve' AND expires_at IS NOT NULL AND expires_at > created_at) OR "
            "(action = 'revoke' AND expires_at IS NULL)",
            name="ck_advisor_action",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    report_digest: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("advisor_reports.digest", ondelete="RESTRICT"),
        nullable=False,
    )
    issuer: Mapped[str] = mapped_column(String(500), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    reason: Mapped[str] = mapped_column(String(2000), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
