"""Session model — maps to the ``sessions`` table (LLD § 7.4).

Columns:
    id          — UUID primary key
    user_id     — FK to users.id
    started_at  — session start timestamp
    ended_at    — session end timestamp (nullable — null means active)
    intent      — 'life' | 'health' | 'unclear' (nullable until classified)

Each session maps to one conversation / recommendation flow.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    intent: Mapped[str | None] = mapped_column(String(20), nullable=True)
