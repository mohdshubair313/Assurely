"""008: durable current turn binding and append-only release decision receipts."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "008_report_release"
down_revision = "007_advisor_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_heads",
        sa.Column("issuer", sa.String(500), primary_key=True),
        sa.Column(
            "session_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("owner_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("turn_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "report_digest",
            sa.String(64),
            sa.ForeignKey("advisor_reports.digest", ondelete="RESTRICT"),
        ),
        sa.Column("guardrail_approved", sa.Boolean, nullable=False),
        sa.CheckConstraint(
            "status IN ('running', 'complete', 'failed')", name="ck_report_head_status"
        ),
        sa.CheckConstraint(
            "status = 'complete' OR (report_digest IS NULL AND NOT guardrail_approved)",
            name="ck_report_head_pending",
        ),
    )
    op.create_table(
        "report_release_receipts",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("issuer", sa.String(500), nullable=False),
        sa.Column(
            "session_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("owner_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("turn_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "report_digest",
            sa.String(64),
            sa.ForeignKey("advisor_reports.digest", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "advisor_event_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("advisor_decisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("request_key", pg.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("issuer", "owner_id", "request_key", name="uq_release_request"),
    )
    op.execute(
        "CREATE TRIGGER release_receipts_immutable BEFORE UPDATE OR DELETE "
        "ON report_release_receipts FOR EACH ROW EXECUTE FUNCTION advisor_review_immutable()"
    )


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM report_heads)
           OR EXISTS (SELECT 1 FROM report_release_receipts) THEN
            RAISE EXCEPTION 'Refusing downgrade while report release records exist';
        END IF;
    END $$""")
    op.drop_table("report_release_receipts")
    op.drop_table("report_heads")
