"""Managed voice intents and separate test billing periods; preserve 011-013."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "014_voice_managed"
down_revision = "013_vaani_backend"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_recaps",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
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
        sa.Column("request_key", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("report_digest", sa.String(64), nullable=False),
        sa.Column("encrypted_content", sa.Text()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "request_key", name="uq_voice_recap_request"),
    )
    op.create_table(
        "voice_managed_operations",
        sa.Column(
            "session_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("voice_sessions.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("phase", sa.String(30), nullable=False),
        sa.Column("encrypted_token", sa.Text()),
        sa.Column("encrypted_connection", sa.Text()),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("end_requested", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("error_category", sa.String(80)),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_voice_managed_pending", "voice_managed_operations", ["phase", "updated_at"])
    op.create_table(
        "voice_subscriptions",
        sa.Column("id", sa.String(120), primary_key=True),
        sa.Column(
            "user_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("request_key", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", sa.String(120), nullable=False),
        sa.Column("external_id", sa.String(120), unique=True),
        sa.Column("included_seconds", sa.Integer(), nullable=False),
        sa.CheckConstraint("included_seconds > 0", name="ck_voice_subscription_allowance"),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("last_event_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "request_key", name="uq_voice_subscription_request"),
    )
    op.create_table(
        "voice_funding_periods",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("subscription_id", sa.String(120), nullable=False),
        sa.Column("plan_id", sa.String(120), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("included_seconds", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.UniqueConstraint("subscription_id", "period_start", name="uq_voice_funding_period"),
        sa.CheckConstraint(
            "period_end > period_start AND included_seconds > 0", name="ck_voice_funding_period"
        ),
    )
    op.create_table(
        "voice_billing_receipts",
        sa.Column("id", sa.String(120), primary_key=True),
        sa.Column("digest", sa.String(64), nullable=False, unique=True),
        sa.Column("event", sa.String(80), nullable=False),
        sa.Column("subscription_id", sa.String(120), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_table(
        "voice_funding_allocations",
        sa.Column(
            "session_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("voice_sessions.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "period_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("voice_funding_periods.id", ondelete="RESTRICT"),
            nullable=False,
        ),
    )
    op.execute("""CREATE TRIGGER voice_funding_allocation_immutable
        BEFORE UPDATE OR DELETE ON voice_funding_allocations
        FOR EACH ROW EXECUTE FUNCTION reject_voice_ledger_edit()""")
    op.execute("""CREATE FUNCTION check_voice_period_integrity() RETURNS trigger
    LANGUAGE plpgsql AS $$
    DECLARE sid uuid; pid uuid; period voice_funding_periods; used bigint;
    BEGIN
      IF TG_TABLE_NAME='voice_sessions' THEN sid:=NEW.id;
      ELSE sid:=NEW.session_id; END IF;
      SELECT period_id INTO pid FROM voice_funding_allocations WHERE session_id=sid;
      IF pid IS NULL THEN RETURN NULL; END IF;
      SELECT * INTO period FROM voice_funding_periods WHERE id=pid FOR UPDATE;
      IF EXISTS (SELECT 1 FROM voice_funding_allocations a JOIN voice_sessions s
          ON s.id=a.session_id WHERE a.period_id=pid AND s.user_id<>period.user_id) THEN
        RAISE EXCEPTION 'Funding owner mismatch' USING ERRCODE='23514';
      END IF;
      SELECT coalesce(sum(CASE WHEN s.state IN ('reserved','active') THEN s.reserved_seconds
        ELSE s.consumed_seconds END),0) INTO used FROM voice_funding_allocations a
        JOIN voice_sessions s ON s.id=a.session_id WHERE a.period_id=pid;
      IF used>period.included_seconds THEN
        RAISE EXCEPTION 'Funding period overspent' USING ERRCODE='23514';
      END IF;
      RETURN NULL;
    END $$""")
    for table in ("voice_sessions", "voice_funding_allocations"):
        op.execute(f"""CREATE CONSTRAINT TRIGGER {table}_period_integrity
          AFTER INSERT OR UPDATE ON {table} DEFERRABLE INITIALLY DEFERRED
          FOR EACH ROW EXECUTE FUNCTION check_voice_period_integrity()""")
    op.execute("""CREATE FUNCTION preserve_voice_funding() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='DELETE' OR NEW.user_id IS DISTINCT FROM OLD.user_id
        OR NEW.subscription_id IS DISTINCT FROM OLD.subscription_id
        OR NEW.plan_id IS DISTINCT FROM OLD.plan_id
        OR NEW.period_start IS DISTINCT FROM OLD.period_start
        OR NEW.period_end IS DISTINCT FROM OLD.period_end
        OR NEW.included_seconds IS DISTINCT FROM OLD.included_seconds THEN
        RAISE EXCEPTION 'Voice funding history is immutable' USING ERRCODE='23514';
      END IF;
      IF NEW.status IS DISTINCT FROM OLD.status
        AND NOT (OLD.status='funded_test' AND NEW.status='available_test') THEN
        RAISE EXCEPTION 'Funding transition is invalid' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$""")
    op.execute("""CREATE TRIGGER voice_funding_immutable BEFORE UPDATE OR DELETE
        ON voice_funding_periods
        FOR EACH ROW EXECUTE FUNCTION preserve_voice_funding()""")
    op.execute("""CREATE FUNCTION preserve_voice_subscription() RETURNS trigger
      LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP='DELETE' OR NEW.id IS DISTINCT FROM OLD.id
        OR NEW.user_id IS DISTINCT FROM OLD.user_id
        OR NEW.request_key IS DISTINCT FROM OLD.request_key
        OR NEW.plan_id IS DISTINCT FROM OLD.plan_id
        OR NEW.included_seconds IS DISTINCT FROM OLD.included_seconds
        OR (OLD.external_id IS NOT NULL AND NEW.external_id IS DISTINCT FROM OLD.external_id) THEN
        RAISE EXCEPTION 'Subscription binding is immutable' USING ERRCODE='23514';
      END IF; RETURN NEW; END $$""")
    op.execute("""CREATE TRIGGER voice_subscription_immutable BEFORE UPDATE OR DELETE
      ON voice_subscriptions FOR EACH ROW EXECUTE FUNCTION preserve_voice_subscription()""")
    op.execute("""CREATE TRIGGER voice_billing_receipt_immutable BEFORE UPDATE OR DELETE
      ON voice_billing_receipts FOR EACH ROW EXECUTE FUNCTION reject_voice_ledger_edit()""")


def downgrade() -> None:
    for table in (
        "voice_funding_allocations",
        "voice_recaps",
        "voice_managed_operations",
        "voice_subscriptions",
        "voice_funding_periods",
        "voice_billing_receipts",
    ):
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table})")):
            raise RuntimeError(
                "Retain voice operations and financial history; operator migration required"
            )
    op.execute("DROP TRIGGER voice_funding_immutable ON voice_funding_periods")
    op.execute("DROP FUNCTION preserve_voice_funding()")
    op.execute("DROP TRIGGER voice_subscription_immutable ON voice_subscriptions")
    op.execute("DROP FUNCTION preserve_voice_subscription()")
    for table in ("voice_sessions", "voice_funding_allocations"):
        op.execute(f"DROP TRIGGER {table}_period_integrity ON {table}")
    op.execute("DROP FUNCTION check_voice_period_integrity()")
    for table in (
        "voice_funding_allocations",
        "voice_recaps",
        "voice_billing_receipts",
        "voice_funding_periods",
        "voice_subscriptions",
        "voice_managed_operations",
    ):
        op.drop_table(table)
