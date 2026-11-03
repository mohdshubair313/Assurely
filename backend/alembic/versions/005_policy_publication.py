"""005: additive immutable, capability-scoped policy publication records."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "005_policy_publication"
down_revision = "004_policy_review_staging"
branch_labels = None
depends_on = None
TABLES = ("policy_publications", "policy_publication_events")


def upgrade() -> None:
    op.create_table(
        "policy_publications",
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column(
            "draft_digest",
            sa.String(64),
            sa.ForeignKey("policy_review_drafts.digest", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("identity_key", sa.String(64), nullable=False),
        sa.Column("payload", pg.JSONB, nullable=False),
        sa.Column("created_by", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("issuer", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_policy_publications_identity_key", "policy_publications", ["identity_key"])
    op.create_table(
        "policy_publication_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "publication_digest",
            sa.String(64),
            sa.ForeignKey("policy_publications.digest", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "representation_event_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("policy_review_events.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("reviewer_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("issuer", sa.String(512), nullable=False),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("publication_digest", "revision"),
        sa.CheckConstraint("revision > 0"),
        sa.CheckConstraint("action IN ('publish', 'revoke')"),
        sa.CheckConstraint("(action = 'publish') = (expires_at IS NOT NULL)"),
    )
    for table in TABLES:
        op.execute(
            f"CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION policy_review_immutable()"
        )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
