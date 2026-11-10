"""Customer review requests preserve separate report-bound advisor authority."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "015_human_review_requests"
down_revision = "014_voice_managed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "human_review_requests",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("issuer", sa.String(500), nullable=False),
        sa.Column(
            "owner_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("request_key", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column(
            "escalation_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("escalations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.UniqueConstraint("issuer", "owner_id", "request_key", name="uq_human_review_request"),
        sa.CheckConstraint("request_digest ~ '^[a-f0-9]{64}$'", name="ck_human_review_digest"),
        sa.CheckConstraint("length(btrim(issuer)) > 0", name="ck_human_review_issuer"),
    )
    op.create_index(
        "ix_human_review_case", "human_review_requests", ["issuer", "session_id", "requested_at"]
    )
    op.create_index(
        "ix_human_review_owner", "human_review_requests", ["issuer", "owner_id", "requested_at"]
    )
    op.execute("""CREATE FUNCTION preserve_human_review_request() RETURNS trigger
      LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'Human review requests are immutable' USING ERRCODE='23514';
      END IF;
      IF NOT EXISTS (SELECT 1 FROM sessions WHERE id=NEW.session_id AND user_id=NEW.owner_id)
        OR NOT EXISTS (SELECT 1 FROM escalations WHERE id=NEW.escalation_id
                       AND session_id=NEW.session_id) THEN
        RAISE EXCEPTION 'Human review request ownership is invalid' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
      END $$""")
    op.execute("""CREATE TRIGGER human_review_request_integrity
      BEFORE INSERT OR UPDATE OR DELETE ON human_review_requests
      FOR EACH ROW EXECUTE FUNCTION preserve_human_review_request()""")


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM human_review_requests)")):
        raise RuntimeError("Retain customer review request history; operator migration required")
    op.drop_table("human_review_requests")
    op.execute("DROP FUNCTION preserve_human_review_request()")
