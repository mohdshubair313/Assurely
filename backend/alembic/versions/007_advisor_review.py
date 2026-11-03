"""007: immutable advisor report snapshots and explicit review/revocation events."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "007_advisor_review"
down_revision = "006_reviewed_policy_terms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "advisor_reports",
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("issuer", sa.String(500), nullable=False),
        sa.Column(
            "session_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("owner_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot", pg.JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_table(
        "advisor_decisions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "report_digest",
            sa.String(64),
            sa.ForeignKey("advisor_reports.digest", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("issuer", sa.String(500), nullable=False),
        sa.Column("actor_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("request_key", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("report_digest", "revision", name="uq_advisor_revision"),
        sa.UniqueConstraint("issuer", "actor_id", "request_key", name="uq_advisor_request"),
        sa.CheckConstraint("revision > 0", name="ck_advisor_revision"),
        sa.CheckConstraint(
            "(action = 'approve' AND expires_at IS NOT NULL AND expires_at > created_at) OR "
            "(action = 'revoke' AND expires_at IS NULL)",
            name="ck_advisor_action",
        ),
    )
    op.execute("""
        CREATE FUNCTION advisor_review_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Advisor review records are append-only'; END;
        $$
    """)
    for table in ("advisor_reports", "advisor_decisions"):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION advisor_review_immutable()"
        )


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM advisor_reports) THEN
                RAISE EXCEPTION 'Refusing downgrade while advisor review records exist';
            END IF;
        END $$
    """)
    op.drop_table("advisor_decisions")
    op.drop_table("advisor_reports")
    op.execute("DROP FUNCTION advisor_review_immutable()")
