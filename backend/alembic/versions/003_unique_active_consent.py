"""003 — prevent duplicate active consent records per scope.

Revision ID: 003_unique_active_consent
Revises: 002_user_profile_memory
Create Date: 2026-09-27
"""

import sqlalchemy as sa

from alembic import op

revision = "003_unique_active_consent"
down_revision = "002_user_profile_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_consent_records_active_scope",
        "consent_records",
        ["user_id", "scope"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_consent_records_active_scope", table_name="consent_records")
