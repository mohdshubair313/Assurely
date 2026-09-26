"""ConsentRecord model — maps to the ``consent_records`` table (LLD § 7.4).

Columns:
    id          — UUID primary key
    user_id     — FK to users.id
    scope       — what was consented to (e.g., 'process_comparison', 'save_profile')
    granted_at  — when consent was given
    revoked_at  — when consent was revoked (nullable — null means still active)

Consent is timestamped and surfaced as a durable receipt.
Users can revoke at any time via the /v1/consent endpoint.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base


class ConsentRecord(Base):
    __tablename__ = "consent_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(100), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
