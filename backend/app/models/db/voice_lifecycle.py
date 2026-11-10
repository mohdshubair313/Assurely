"""Additive managed operations and test billing history; never provider tokens in plaintext."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base


class VoiceManagedOperation(Base):
    __tablename__ = "voice_managed_operations"
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voice_sessions.id", ondelete="RESTRICT"), primary_key=True
    )
    phase: Mapped[str] = mapped_column(String(30), nullable=False, default="pending_create")
    encrypted_token: Mapped[str | None] = mapped_column(Text)
    encrypted_connection: Mapped[str | None] = mapped_column(Text)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_requested: Mapped[bool] = mapped_column(default=False, nullable=False)
    error_category: Mapped[str | None] = mapped_column(String(80))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class VoiceRecap(Base):
    __tablename__ = "voice_recaps"
    __table_args__ = (UniqueConstraint("user_id", "request_key", name="uq_voice_recap_request"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="RESTRICT"), nullable=False
    )
    request_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    report_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    encrypted_content: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class VoiceFundingPeriod(Base):
    __tablename__ = "voice_funding_periods"
    __table_args__ = (
        UniqueConstraint("subscription_id", "period_start", name="uq_voice_funding_period"),
        CheckConstraint(
            "period_end > period_start AND included_seconds > 0", name="ck_voice_funding_period"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    subscription_id: Mapped[str] = mapped_column(String(120), nullable=False)
    plan_id: Mapped[str] = mapped_column(String(120), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    included_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="funded_test")


class VoiceFundingAllocation(Base):
    __tablename__ = "voice_funding_allocations"
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voice_sessions.id", ondelete="RESTRICT"), primary_key=True
    )
    period_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("voice_funding_periods.id", ondelete="RESTRICT"),
        nullable=False,
    )


class VoiceBillingReceipt(Base):
    __tablename__ = "voice_billing_receipts"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    event: Mapped[str] = mapped_column(String(80), nullable=False)
    subscription_id: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class VoiceSubscription(Base):
    __tablename__ = "voice_subscriptions"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    request_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    plan_id: Mapped[str] = mapped_column(String(120), nullable=False)
    included_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(120), unique=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="created")
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("user_id", "request_key", name="uq_voice_subscription_request"),
    )
