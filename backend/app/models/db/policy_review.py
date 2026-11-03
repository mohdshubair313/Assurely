"""Durable review staging; these records never activate customer policy terms."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base


class PolicySourceBlob(Base):
    __tablename__ = "policy_source_blobs"
    __table_args__ = (CheckConstraint("octet_length(content) <= 20971520"),)
    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class PolicyReviewDraft(Base):
    __tablename__ = "policy_review_drafts"
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    issuer: Mapped[str] = mapped_column(String(512), nullable=False)


class PolicyReviewFact(Base):
    __tablename__ = "policy_review_facts"
    draft_digest: Mapped[str] = mapped_column(
        ForeignKey("policy_review_drafts.digest", ondelete="RESTRICT"),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(String(60), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class PolicyReviewEvent(Base):
    __tablename__ = "policy_review_events"
    __table_args__ = (
        UniqueConstraint("draft_digest", "revision"),
        CheckConstraint("revision > 0"),
        CheckConstraint("action IN ('accept_representation', 'reject', 'revoke')"),
        CheckConstraint("(action = 'accept_representation') = (expires_at IS NOT NULL)"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    draft_digest: Mapped[str] = mapped_column(
        ForeignKey("policy_review_drafts.digest", ondelete="RESTRICT"),
        nullable=False,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(String(2000), nullable=False)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    issuer: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PolicyWorkflowReceipt(Base):
    __tablename__ = "policy_workflow_receipts"
    issuer: Mapped[str] = mapped_column(String(512), primary_key=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    request_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
