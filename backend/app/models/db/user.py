"""User model — maps to the ``users`` table (LLD § 7.4).

Columns:
    id          — UUID primary key
    phone_hash  — hashed phone number (nullable, unique)
    email_hash  — hashed email (nullable, unique)
    role        — 'customer' | 'advisor' | 'admin'
    tenant_id   — nullable UUID, reserved for future white-label partners
    created_at  — timestamp with timezone

Role gates what a session can do:
  - customer: sees only their own sessions
  - advisor: sees only cases assigned via escalations.assigned_advisor
  - admin: full access
"""

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    phone_hash: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    email_hash: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, server_default="customer")
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
