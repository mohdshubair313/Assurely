"""PolicyDocument model — maps to the ``policy_documents`` table (LLD § 7.4).

Columns:
    id            — UUID primary key
    insurer       — insurer name
    product_name  — specific product name
    doc_url       — URL or path to the source document
    ingested_at   — when the document was ingested into the system
    version_hash  — SHA-256 of the document content for versioning

Each policy_document can have multiple policy_terms versions
as terms are updated over time. The version_hash lets us detect
when a document has changed and needs re-ingestion.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base


class PolicyDocument(Base):
    __tablename__ = "policy_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    insurer: Mapped[str] = mapped_column(String(200), nullable=False)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    doc_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    version_hash: Mapped[str] = mapped_column(String(64), nullable=False)
