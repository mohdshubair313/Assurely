"""Fence completed checkpoint selection and audit orphan-turn recovery."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "009_turn_recovery"
down_revision = "008_report_release"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("report_heads", sa.Column("completed_turn_id", pg.UUID(as_uuid=True)))
    op.create_table(
        "turn_recovery_receipts",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("issuer", sa.String(500), nullable=False),
        sa.Column("session_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("sessions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("owner_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("turn_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("request_key", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("issuer", "owner_id", "request_key", name="uq_turn_recovery_key"),
    )
    op.execute("CREATE TRIGGER turn_recovery_immutable BEFORE UPDATE OR DELETE "
               "ON turn_recovery_receipts FOR EACH ROW EXECUTE FUNCTION advisor_review_immutable()")


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM turn_recovery_receipts)
           OR EXISTS (SELECT 1 FROM report_heads WHERE completed_turn_id IS NOT NULL) THEN
            RAISE EXCEPTION 'Refusing downgrade while durable turn records exist';
        END IF;
    END $$""")
    op.drop_table("turn_recovery_receipts")
    op.drop_column("report_heads", "completed_turn_id")
