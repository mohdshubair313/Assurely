"""Minimal Vaani bindings and authenticated event receipts; no transcripts or tokens."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base


class VoiceProviderCall(Base):
    __tablename__ = "voice_provider_calls"
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voice_sessions.id", ondelete="RESTRICT"), primary_key=True
    )
    room: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    phase: Mapped[str] = mapped_column(String(30), nullable=False, server_default="ready")
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    measured_seconds: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    byol_connection_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    byol_lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_response_id: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class VoiceProviderEvent(Base):
    __tablename__ = "voice_provider_events"
    __table_args__ = (Index("ix_voice_provider_events_status", "status", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    digest: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    event: Mapped[str] = mapped_column(String(80), nullable=False)
    room: Mapped[str] = mapped_column(String(160), nullable=False)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="received")
    reason: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
