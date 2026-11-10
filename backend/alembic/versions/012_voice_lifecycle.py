"""Harden mock voice lifecycle without changing applied migration 011."""

import hashlib
import json
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "012_voice_lifecycle"
down_revision = "011_voice_entitlements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("voice_sessions", sa.Column("request_digest", sa.String(64)))
    op.add_column("voice_sessions", sa.Column("expires_at", sa.DateTime(timezone=True)))
    op.add_column("voice_sessions", sa.Column("recovery_after", sa.DateTime(timezone=True)))
    db = op.get_bind()
    # Only persisted request fields are hashed. Do not relabel consent or alter usage.
    for row in db.execute(sa.text("SELECT id, language FROM voice_sessions")).mappings():
        digest = hashlib.sha256(
            json.dumps(
                {"language": row["language"]}, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        db.execute(
            sa.text("UPDATE voice_sessions SET request_digest=:digest WHERE id=:id"),
            {"digest": digest, "id": row["id"]},
        )
    db.execute(
        sa.text("""
        UPDATE voice_sessions SET
          expires_at=created_at + reserved_seconds * interval '1 second',
          recovery_after=created_at + interval '30 seconds'
    """)
    )
    for name in ("request_digest", "expires_at", "recovery_after"):
        op.alter_column("voice_sessions", name, nullable=False)
    op.drop_constraint("voice_sessions_idempotency_key_key", "voice_sessions", type_="unique")
    op.create_unique_constraint(
        "uq_voice_session_owner_key", "voice_sessions", ["user_id", "idempotency_key"]
    )
    op.create_index("ix_voice_sessions_due", "voice_sessions", ["provider", "state", "expires_at"])
    op.create_check_constraint(
        "ck_voice_entitlement_balance",
        "voice_entitlements",
        "consumed_seconds + reserved_seconds <= included_seconds",
    )
    op.create_check_constraint(
        "ck_voice_entitlement_period", "voice_entitlements", "period_end > period_start"
    )
    op.create_check_constraint(
        "ck_voice_entitlement_call_cap", "voice_entitlements", "max_call_seconds > 0"
    )
    op.create_check_constraint(
        "ck_voice_session_balance", "voice_sessions", "consumed_seconds <= reserved_seconds"
    )
    op.create_unique_constraint(
        "uq_voice_ledger_session_operation", "voice_usage_ledger", ["session_id", "entry_type"]
    )
    op.create_check_constraint("ck_voice_ledger_seconds", "voice_usage_ledger", "seconds >= 0")
    op.create_check_constraint(
        "ck_voice_ledger_kind",
        "voice_usage_ledger",
        "entry_type IN ('reservation','settlement','release')",
    )
    op.create_table(
        "voice_operations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("operation", sa.String(20), nullable=False),
        sa.Column("request_key", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column(
            "session_id", pg.UUID(as_uuid=True), sa.ForeignKey("voice_sessions.id"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "operation", "request_key", name="uq_voice_operation_key"),
        sa.CheckConstraint("operation IN ('start','end')", name="ck_voice_operation_kind"),
    )
    for row in db.execute(
        sa.text("SELECT id,user_id,idempotency_key,request_digest,created_at FROM voice_sessions")
    ).mappings():
        db.execute(
            sa.text("""
            INSERT INTO voice_operations
            (id,user_id,operation,request_key,request_digest,session_id,created_at)
            VALUES (:id,:user_id,'start',:key,:digest,:session_id,:created_at)
        """),
            {
                "id": uuid.uuid4(),
                "user_id": row["user_id"],
                "key": row["idempotency_key"],
                "digest": row["request_digest"],
                "session_id": row["id"],
                "created_at": row["created_at"],
            },
        )
    # A ledger is append-only. Corrections must be reviewed, not hidden by editing history.
    db.execute(
        sa.text("""
        CREATE FUNCTION reject_voice_identity_change() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.user_id IS DISTINCT FROM OLD.user_id
            OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
            OR NEW.request_digest IS DISTINCT FROM OLD.request_digest
            OR NEW.reserved_seconds IS DISTINCT FROM OLD.reserved_seconds THEN
            RAISE EXCEPTION 'Voice session identity is immutable' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
    """)
    )
    op.execute("""CREATE TRIGGER voice_session_identity_immutable BEFORE UPDATE ON voice_sessions
        FOR EACH ROW EXECUTE FUNCTION reject_voice_identity_change()""")
    db.execute(
        sa.text("""
        CREATE FUNCTION reject_voice_ledger_edit() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Voice ledger entries are immutable' USING ERRCODE='23514'; END $$
    """)
    )
    db.execute(
        sa.text("""
        CREATE TRIGGER voice_ledger_immutable BEFORE UPDATE OR DELETE ON voice_usage_ledger
        FOR EACH ROW EXECUTE FUNCTION reject_voice_ledger_edit()
    """)
    )
    # Deferred validation sees the complete reservation/settlement transaction. It also
    # rejects inconsistent privileged SQL writes instead of letting a later request mask them.
    db.execute(
        sa.text("""
        CREATE FUNCTION check_voice_integrity() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE eid uuid; ent voice_entitlements; reserved bigint; used bigint; released bigint;
        BEGIN
          IF TG_TABLE_NAME='voice_entitlements' THEN eid:=NEW.id;
          ELSIF TG_TABLE_NAME='voice_sessions' THEN
            SELECT id INTO eid FROM voice_entitlements WHERE user_id=NEW.user_id;
          ELSE eid:=NEW.entitlement_id; END IF;
          SELECT * INTO ent FROM voice_entitlements WHERE id=eid FOR UPDATE;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'Voice funding is missing' USING ERRCODE='23514';
          END IF;
          SELECT coalesce(sum(seconds) FILTER (WHERE entry_type='reservation'),0),
                 coalesce(sum(seconds) FILTER (WHERE entry_type='settlement'),0),
                 coalesce(sum(seconds) FILTER (WHERE entry_type='release'),0)
            INTO reserved,used,released FROM voice_usage_ledger WHERE entitlement_id=eid;
          IF ent.reserved_seconds <> reserved-used-released OR ent.consumed_seconds <> used
             OR EXISTS (SELECT 1 FROM voice_usage_ledger l JOIN voice_sessions s
                        ON s.id=l.session_id WHERE l.entitlement_id=eid AND s.user_id<>ent.user_id)
             OR EXISTS (
               SELECT 1 FROM voice_sessions s WHERE s.user_id=ent.user_id AND (
                 s.reserved_seconds <> coalesce((SELECT sum(l.seconds) FROM voice_usage_ledger l
                   WHERE l.session_id=s.id AND l.entry_type='reservation'),0)
                 OR s.consumed_seconds <> coalesce((SELECT sum(l.seconds) FROM voice_usage_ledger l
                   WHERE l.session_id=s.id AND l.entry_type='settlement'),0)
                 OR (s.state IN ('reserved','active') AND EXISTS (
                   SELECT 1 FROM voice_usage_ledger l WHERE l.session_id=s.id
                     AND l.entry_type IN ('settlement','release')))
                 OR (s.state NOT IN ('reserved','active') AND s.reserved_seconds <>
                   coalesce((SELECT sum(l.seconds) FROM voice_usage_ledger l
                     WHERE l.session_id=s.id AND l.entry_type IN ('settlement','release')),0))
               )
             ) THEN
            RAISE EXCEPTION 'Voice ledger and balances disagree' USING ERRCODE='23514';
          END IF;
          RETURN NULL;
        END $$
    """)
    )
    for table in ("voice_entitlements", "voice_sessions", "voice_usage_ledger"):
        op.execute(f"""CREATE CONSTRAINT TRIGGER {table}_integrity
            AFTER INSERT OR UPDATE ON {table} DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION check_voice_integrity()""")
    # Validate existing rows too; never repair unexplained balances during migration.
    op.execute("UPDATE voice_entitlements SET updated_at=updated_at")


def downgrade() -> None:
    # Global key uniqueness cannot be restored after valid cross-user reuse.
    if op.get_bind().scalar(
        sa.text("""
        SELECT EXISTS (SELECT 1 FROM voice_sessions GROUP BY idempotency_key HAVING count(*) > 1)
    """)
    ):
        raise RuntimeError("Cannot downgrade scoped voice keys without an operator migration")
    for table in ("voice_entitlements", "voice_sessions", "voice_usage_ledger"):
        op.execute(f"DROP TRIGGER {table}_integrity ON {table}")
    op.execute("DROP FUNCTION check_voice_integrity()")
    op.execute("DROP TRIGGER voice_session_identity_immutable ON voice_sessions")
    op.execute("DROP FUNCTION reject_voice_identity_change()")
    op.execute("DROP TRIGGER voice_ledger_immutable ON voice_usage_ledger")
    op.execute("DROP FUNCTION reject_voice_ledger_edit()")
    op.drop_table("voice_operations")
    for table, name in [
        ("voice_usage_ledger", "ck_voice_ledger_kind"),
        ("voice_usage_ledger", "ck_voice_ledger_seconds"),
        ("voice_sessions", "ck_voice_session_balance"),
        ("voice_entitlements", "ck_voice_entitlement_call_cap"),
        ("voice_entitlements", "ck_voice_entitlement_period"),
        ("voice_entitlements", "ck_voice_entitlement_balance"),
    ]:
        op.drop_constraint(name, table, type_="check")
    op.drop_constraint("uq_voice_ledger_session_operation", "voice_usage_ledger", type_="unique")
    op.drop_index("ix_voice_sessions_due", table_name="voice_sessions")
    op.drop_constraint("uq_voice_session_owner_key", "voice_sessions", type_="unique")
    op.create_unique_constraint(
        "voice_sessions_idempotency_key_key", "voice_sessions", ["idempotency_key"]
    )
    for name in ("request_digest", "expires_at", "recovery_after"):
        op.drop_column("voice_sessions", name)
