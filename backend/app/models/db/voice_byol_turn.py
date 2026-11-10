"""Minimal durable response fences; never retain transcripts or insurance text."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base


class VoiceByolTurn(Base):
    __tablename__ = "voice_byol_turns"
    __table_args__ = (UniqueConstraint("session_id", "response_id", name="uq_byol_turn_response"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voice_provider_calls.session_id", ondelete="RESTRICT")
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    response_id: Mapped[int] = mapped_column(Integer)
    request_digest: Mapped[str] = mapped_column(String(64))
    intent: Mapped[str] = mapped_column(String(20))
    state: Mapped[str] = mapped_column(String(20), default="pending")
    answer_kind: Mapped[str | None] = mapped_column(String(20))
    binding_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voice_case_bindings.id", ondelete="RESTRICT")
    )
    answer_digest: Mapped[str | None] = mapped_column(String(64))
    source_digest: Mapped[str | None] = mapped_column(String(64))
    authorization_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )
    prepared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
