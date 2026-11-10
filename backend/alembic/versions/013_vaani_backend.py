"""Minimal Vaani event inbox and synthetic provider-call bindings; preserve 012."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "013_vaani_backend"
down_revision = "012_voice_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_provider_calls",
        sa.Column(
            "session_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("voice_sessions.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("room", sa.String(160), nullable=False, unique=True),
        sa.Column("agent_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("synthetic", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("phase", sa.String(30), nullable=False, server_default="ready"),
        sa.Column("last_event_at", sa.DateTime(timezone=True)),
        sa.Column("measured_seconds", sa.Numeric(12, 3)),
        sa.Column("byol_connection_id", pg.UUID(as_uuid=True)),
        sa.Column("byol_lease_until", sa.DateTime(timezone=True)),
        sa.Column("last_response_id", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("last_response_id >= 0", name="ck_vaani_response_id"),
        sa.CheckConstraint(
            "measured_seconds IS NULL OR measured_seconds >= 0", name="ck_vaani_measured"
        ),
    )
    op.create_table(
        "voice_provider_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("digest", sa.String(64), nullable=False, unique=True),
        sa.Column("event", sa.String(80), nullable=False),
        sa.Column("room", sa.String(160), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration", sa.Numeric(12, 3)),
        sa.Column("status", sa.String(30), nullable=False, server_default="received"),
        sa.Column("reason", sa.String(80)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("duration IS NULL OR duration >= 0", name="ck_vaani_event_duration"),
    )
    op.create_index(
        "ix_voice_provider_events_status", "voice_provider_events", ["status", "created_at"]
    )
    op.execute("""
        CREATE FUNCTION preserve_vaani_binding() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP='DELETE' OR NEW.session_id IS DISTINCT FROM OLD.session_id
             OR NEW.room IS DISTINCT FROM OLD.room OR NEW.agent_id IS DISTINCT FROM OLD.agent_id
             OR NEW.synthetic IS DISTINCT FROM OLD.synthetic THEN
            RAISE EXCEPTION 'Provider binding is immutable' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
    """)
    op.execute("""CREATE TRIGGER vaani_binding_immutable BEFORE UPDATE OR DELETE
        ON voice_provider_calls FOR EACH ROW EXECUTE FUNCTION preserve_vaani_binding()""")
    op.execute("""
        CREATE FUNCTION preserve_vaani_event() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP='DELETE' OR NEW.digest IS DISTINCT FROM OLD.digest
             OR NEW.event IS DISTINCT FROM OLD.event OR NEW.room IS DISTINCT FROM OLD.room
             OR NEW.event_at IS DISTINCT FROM OLD.event_at
             OR NEW.duration IS DISTINCT FROM OLD.duration THEN
            RAISE EXCEPTION 'Provider receipt is immutable' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
    """)
    op.execute("""CREATE TRIGGER vaani_event_immutable BEFORE UPDATE OR DELETE
        ON voice_provider_events FOR EACH ROW EXECUTE FUNCTION preserve_vaani_event()""")


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM voice_provider_calls)")
    ) or op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM voice_provider_events)")):
        raise RuntimeError("Archive provider audit records before an operator-reviewed downgrade")
    op.execute("DROP TRIGGER vaani_event_immutable ON voice_provider_events")
    op.execute("DROP FUNCTION preserve_vaani_event()")
    op.execute("DROP TRIGGER vaani_binding_immutable ON voice_provider_calls")
    op.execute("DROP FUNCTION preserve_vaani_binding()")
    op.drop_index("ix_voice_provider_events_status", table_name="voice_provider_events")
    op.drop_table("voice_provider_events")
    op.drop_table("voice_provider_calls")
