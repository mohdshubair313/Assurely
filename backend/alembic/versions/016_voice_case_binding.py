"""Immutable reviewed-case selection for voice display, never a release bypass."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "016_voice_case_binding"
down_revision = "015_human_review_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_case_bindings",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "voice_session_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("voice_sessions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("issuer", sa.String(500), nullable=False),
        sa.Column(
            "owner_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "case_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("turn_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "report_digest",
            sa.String(64),
            sa.ForeignKey("advisor_reports.digest", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("request_key", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("release_request_key", pg.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "release_receipt_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("report_release_receipts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "advisor_event_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("advisor_decisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.UniqueConstraint("voice_session_id", name="uq_voice_case_session"),
        sa.UniqueConstraint("issuer", "owner_id", "request_key", name="uq_voice_case_request"),
        sa.CheckConstraint("length(btrim(issuer)) > 0", name="ck_voice_case_issuer"),
        sa.CheckConstraint("request_digest ~ '^[a-f0-9]{64}$'", name="ck_voice_case_digest"),
    )
    op.execute("""CREATE FUNCTION preserve_voice_case_binding() RETURNS trigger
      LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'Voice case bindings are immutable' USING ERRCODE='23514';
      END IF;
      IF NOT EXISTS (SELECT 1 FROM voice_sessions v WHERE v.id=NEW.voice_session_id
        AND v.user_id=NEW.owner_id AND v.source_mode='synthetic-vaani')
        OR NOT EXISTS (SELECT 1 FROM sessions s WHERE s.id=NEW.case_id
          AND s.user_id=NEW.owner_id)
        OR NOT EXISTS (SELECT 1 FROM report_release_receipts r
          WHERE r.id=NEW.release_receipt_id AND r.issuer=NEW.issuer
          AND r.owner_id=NEW.owner_id AND r.session_id=NEW.case_id
          AND r.turn_id=NEW.turn_id AND r.report_digest=NEW.report_digest
          AND r.advisor_event_id=NEW.advisor_event_id
          AND r.request_key=NEW.release_request_key) THEN
        RAISE EXCEPTION 'Voice case binding scope is invalid' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
      END $$""")
    op.execute("""CREATE TRIGGER voice_case_binding_integrity
      BEFORE INSERT OR UPDATE OR DELETE ON voice_case_bindings
      FOR EACH ROW EXECUTE FUNCTION preserve_voice_case_binding()""")


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM voice_case_bindings)")):
        raise RuntimeError("Retain voice binding history; operator migration required")
    op.drop_table("voice_case_bindings")
    op.execute("DROP FUNCTION preserve_voice_case_binding()")
