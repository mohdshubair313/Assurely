"""Immutable publication proposals and authenticated publication/revocation events."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base


class PolicyPublication(Base):
    __tablename__ = "policy_publications"
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    draft_digest: Mapped[str] = mapped_column(
        ForeignKey("policy_review_drafts.digest", ondelete="RESTRICT"), nullable=False
    )
    identity_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    issuer: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PolicyPublicationEvent(Base):
    __tablename__ = "policy_publication_events"
    __table_args__ = (
        UniqueConstraint("publication_digest", "revision"),
        CheckConstraint("revision > 0"),
        CheckConstraint("action IN ('publish', 'revoke')"),
        CheckConstraint("(action = 'publish') = (expires_at IS NOT NULL)"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    publication_digest: Mapped[str] = mapped_column(
        ForeignKey("policy_publications.digest", ondelete="RESTRICT"), nullable=False
    )
    representation_event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("policy_review_events.id", ondelete="RESTRICT"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    issuer: Mapped[str] = mapped_column(String(512), nullable=False)
    reason: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
