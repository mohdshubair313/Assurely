"""Persistent voice entitlements, sessions and idempotent usage ledger."""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base


class VoiceEntitlement(Base):
    __tablename__ = "voice_entitlements"
    __table_args__ = (
        CheckConstraint("included_seconds >= 0", name="ck_voice_entitlement_included"),
        CheckConstraint("reserved_seconds >= 0", name="ck_voice_entitlement_reserved"),
        CheckConstraint("consumed_seconds >= 0", name="ck_voice_entitlement_consumed"),
        CheckConstraint(
            "consumed_seconds + reserved_seconds <= included_seconds",
            name="ck_voice_entitlement_balance",
        ),
        CheckConstraint("period_end > period_start", name="ck_voice_entitlement_period"),
        CheckConstraint("max_call_seconds > 0", name="ck_voice_entitlement_call_cap"),
        CheckConstraint(
            "concurrency_limit BETWEEN 1 AND 5", name="ck_voice_entitlement_concurrency"
        ),
        Index("ix_voice_entitlements_status_period", "status", "period_end"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    external_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    plan_code: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    included_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    consumed_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    concurrency_limit: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    max_call_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="300")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class VoiceSession(Base):
    __tablename__ = "voice_sessions"
    __table_args__ = (
        CheckConstraint("reserved_seconds >= 0", name="ck_voice_session_reserved"),
        CheckConstraint("consumed_seconds >= 0", name="ck_voice_session_consumed"),
        CheckConstraint("consumed_seconds <= reserved_seconds", name="ck_voice_session_balance"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_voice_session_owner_key"),
        Index("ix_voice_sessions_due", "provider", "state", "expires_at"),
        Index("ix_voice_sessions_owner_state", "user_id", "state"),
        Index("ix_voice_sessions_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    case_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_call_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    room_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str] = mapped_column(String(30), nullable=False)
    language: Mapped[str] = mapped_column(String(20), nullable=False)
    idempotency_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recovery_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reserved_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    consumed_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    consent_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    source_mode: Mapped[str] = mapped_column(String(40), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(80), nullable=False)
    error_category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VoiceUsageLedger(Base):
    __tablename__ = "voice_usage_ledger"
    __table_args__ = (
        Index("ix_voice_ledger_entitlement_created", "entitlement_id", "created_at"),
        UniqueConstraint("session_id", "entry_type", name="uq_voice_ledger_session_operation"),
        CheckConstraint("seconds >= 0", name="ck_voice_ledger_seconds"),
        CheckConstraint(
            "entry_type IN ('reservation','settlement','release')", name="ck_voice_ledger_kind"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    entitlement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voice_entitlements.id", ondelete="RESTRICT"), nullable=False
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voice_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    entry_type: Mapped[str] = mapped_column(String(30), nullable=False)
    seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    settlement_reference: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    source_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class VoiceOperation(Base):
    """Durable, user/operation-scoped request receipts (no provider credentials)."""

    __tablename__ = "voice_operations"
    __table_args__ = (
        UniqueConstraint("user_id", "operation", "request_key", name="uq_voice_operation_key"),
        CheckConstraint("operation IN ('start','end')", name="ck_voice_operation_kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    operation: Mapped[str] = mapped_column(String(20), nullable=False)
    request_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voice_sessions.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
