"""Durable one-shot provider response fences; no transcript or speech storage."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "017_voice_byol_turns"
down_revision = "016_voice_case_binding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_byol_turns",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("voice_provider_calls.session_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("connection_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("response_id", sa.Integer(), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("intent", sa.String(20), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("answer_kind", sa.String(20)),
        sa.Column(
            "binding_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("voice_case_bindings.id", ondelete="RESTRICT"),
        ),
        sa.Column("answer_digest", sa.String(64)),
        sa.Column("source_digest", sa.String(64)),
        sa.Column("authorization_expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column("prepared_at", sa.DateTime(timezone=True)),
        sa.Column("attempted_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("session_id", "response_id", name="uq_byol_turn_response"),
        sa.CheckConstraint("response_id BETWEEN 1 AND 2147483647", name="ck_byol_response_id"),
        sa.CheckConstraint("request_digest ~ '^[a-f0-9]{64}$'", name="ck_byol_request_digest"),
        sa.CheckConstraint("intent IN ('report','unsupported')", name="ck_byol_intent"),
        sa.CheckConstraint(
            "state IN ('pending','prepared','send_unknown','sent','interrupted','failed')",
            name="ck_byol_state",
        ),
        sa.CheckConstraint(
            "answer_digest IS NULL OR answer_digest ~ '^[a-f0-9]{64}$'",
            name="ck_byol_answer_digest",
        ),
        sa.CheckConstraint(
            "source_digest IS NULL OR source_digest ~ '^[a-f0-9]{64}$'",
            name="ck_byol_source_digest",
        ),
        sa.CheckConstraint(
            "state NOT IN ('prepared','send_unknown','sent') OR "
            "(answer_kind IS NOT NULL AND answer_digest IS NOT NULL AND prepared_at IS NOT NULL "
            "AND authorization_expires_at IS NOT NULL)",
            name="ck_byol_prepared",
        ),
        sa.CheckConstraint(
            "state NOT IN ('send_unknown','sent') OR attempted_at IS NOT NULL",
            name="ck_byol_attempted",
        ),
        sa.CheckConstraint("state <> 'sent' OR completed_at IS NOT NULL", name="ck_byol_sent"),
        sa.CheckConstraint(
            "(binding_id IS NULL) = (source_digest IS NULL)", name="ck_byol_report_binding"
        ),
        sa.CheckConstraint(
            "intent <> 'unsupported' OR binding_id IS NULL", name="ck_byol_unsupported_binding"
        ),
        sa.CheckConstraint(
            "answer_kind IS NULL OR answer_kind IN ('report','operational')",
            name="ck_byol_answer_kind",
        ),
        sa.CheckConstraint(
            "answer_kind <> 'report' OR "
            "(intent='report' AND binding_id IS NOT NULL AND source_digest IS NOT NULL)",
            name="ck_byol_factual_answer",
        ),
        sa.CheckConstraint(
            "answer_kind <> 'operational' OR (binding_id IS NULL AND source_digest IS NULL)",
            name="ck_byol_operational_answer",
        ),
    )
    op.execute("""CREATE FUNCTION preserve_voice_byol_turn() RETURNS trigger
      LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Retain provider response history' USING ERRCODE='23514';
      END IF;
      IF NOT EXISTS (SELECT 1 FROM voice_sessions v JOIN voice_provider_calls c
        ON c.session_id=v.id WHERE v.id=NEW.session_id AND v.user_id=NEW.owner_id
        AND c.synthetic AND v.source_mode='synthetic-vaani') OR
        (NEW.binding_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM voice_case_bindings b
          WHERE b.id=NEW.binding_id AND b.voice_session_id=NEW.session_id
          AND b.owner_id=NEW.owner_id)) THEN
        RAISE EXCEPTION 'Provider response scope is invalid' USING ERRCODE='23514';
      END IF;
      IF TG_OP='INSERT' THEN
        IF NEW.state <> 'pending' OR NEW.answer_kind IS NOT NULL OR NEW.binding_id IS NOT NULL
          OR NEW.answer_digest IS NOT NULL OR NEW.source_digest IS NOT NULL
          OR NEW.authorization_expires_at IS NOT NULL OR NEW.prepared_at IS NOT NULL
          OR NEW.attempted_at IS NOT NULL OR NEW.completed_at IS NOT NULL THEN
          RAISE EXCEPTION 'Response must begin pending' USING ERRCODE='23514';
        END IF;
      ELSE
        IF ROW(NEW.id,NEW.session_id,NEW.owner_id,NEW.connection_id,NEW.response_id,
          NEW.request_digest,NEW.intent,NEW.created_at) IS DISTINCT FROM
          ROW(OLD.id,OLD.session_id,OLD.owner_id,OLD.connection_id,OLD.response_id,
          OLD.request_digest,OLD.intent,OLD.created_at) THEN
          RAISE EXCEPTION 'Response identity is immutable' USING ERRCODE='23514';
        END IF;
        IF NOT ((OLD.state='pending' AND NEW.state IN ('prepared','interrupted','failed'))
          OR (OLD.state='prepared' AND NEW.state IN ('send_unknown','interrupted','failed'))
          OR (OLD.state='send_unknown' AND NEW.state='sent')) THEN
          RAISE EXCEPTION 'Invalid response transition' USING ERRCODE='23514';
        END IF;
        IF OLD.state <> 'pending' AND
          ROW(NEW.answer_kind,NEW.binding_id,NEW.answer_digest,NEW.source_digest,
            NEW.authorization_expires_at,NEW.prepared_at) IS DISTINCT FROM
          ROW(OLD.answer_kind,OLD.binding_id,OLD.answer_digest,OLD.source_digest,
            OLD.authorization_expires_at,OLD.prepared_at) THEN
          RAISE EXCEPTION 'Prepared response is immutable' USING ERRCODE='23514';
        END IF;
        IF OLD.state='pending' AND NEW.state <> 'prepared' AND
          ROW(NEW.answer_kind,NEW.binding_id,NEW.answer_digest,NEW.source_digest,
            NEW.authorization_expires_at,NEW.prepared_at) IS DISTINCT FROM
          ROW(OLD.answer_kind,OLD.binding_id,OLD.answer_digest,OLD.source_digest,
            OLD.authorization_expires_at,OLD.prepared_at) THEN
          RAISE EXCEPTION 'Unprepared response cannot acquire content' USING ERRCODE='23514';
        END IF;
        IF NEW.state <> 'sent' AND NEW.completed_at IS NOT NULL THEN
          RAISE EXCEPTION 'Unconfirmed send completion' USING ERRCODE='23514';
        END IF;
        IF NEW.state NOT IN ('send_unknown','sent') AND NEW.attempted_at IS NOT NULL THEN
          RAISE EXCEPTION 'Unconfirmed send attempt' USING ERRCODE='23514';
        END IF;
        IF OLD.attempted_at IS NOT NULL AND NEW.attempted_at IS DISTINCT FROM OLD.attempted_at THEN
          RAISE EXCEPTION 'Send attempt is immutable' USING ERRCODE='23514';
        END IF;
      END IF;
      RETURN NEW;
      END $$""")
    op.execute("""CREATE TRIGGER voice_byol_turn_integrity
      BEFORE INSERT OR UPDATE OR DELETE ON voice_byol_turns
      FOR EACH ROW EXECUTE FUNCTION preserve_voice_byol_turn()""")


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM voice_byol_turns)")):
        raise RuntimeError("Retain provider response history; operator migration required")
    op.drop_table("voice_byol_turns")
    op.execute("DROP FUNCTION preserve_voice_byol_turn()")
