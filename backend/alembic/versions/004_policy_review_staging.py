"""004: immutable policy review staging, isolated from runtime policy_terms."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "004_policy_review_staging"
down_revision = "003_unique_active_consent"
branch_labels = None
depends_on = None

TABLES = (
    "policy_source_blobs",
    "policy_review_drafts",
    "policy_review_facts",
    "policy_review_events",
    "policy_workflow_receipts",
)


def upgrade() -> None:
    op.create_table(
        "policy_source_blobs",
        sa.Column("sha256", sa.String(64), primary_key=True),
        sa.Column("content", sa.LargeBinary, nullable=False),
        sa.CheckConstraint("octet_length(content) <= 20971520"),
    )
    op.create_table(
        "policy_review_drafts",
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("payload", pg.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("issuer", sa.String(512), nullable=False),
    )
    op.create_table(
        "policy_review_facts",
        sa.Column(
            "draft_digest",
            sa.String(64),
            sa.ForeignKey("policy_review_drafts.digest", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("name", sa.String(60), primary_key=True),
        sa.Column("payload", pg.JSONB, nullable=False),
    )
    op.create_table(
        "policy_review_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "draft_digest",
            sa.String(64),
            sa.ForeignKey("policy_review_drafts.digest", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column("reviewer_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("issuer", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("draft_digest", "revision"),
        sa.CheckConstraint("revision > 0"),
        sa.CheckConstraint("action IN ('accept_representation', 'reject', 'revoke')"),
        sa.CheckConstraint("(action = 'accept_representation') = (expires_at IS NOT NULL)"),
    )
    op.create_table(
        "policy_workflow_receipts",
        sa.Column("issuer", sa.String(512), primary_key=True),
        sa.Column("actor_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_key", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("result", pg.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    # The application role cannot update/delete staged evidence or historical decisions.
    op.execute("""
        CREATE FUNCTION policy_review_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Policy review records are append-only'; END;
        $$
    """)
    for table in TABLES:
        op.execute(
            f"CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION policy_review_immutable()"
        )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
    op.execute("DROP FUNCTION policy_review_immutable()")
