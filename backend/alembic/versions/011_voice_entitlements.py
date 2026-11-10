"""Add owner-scoped voice sessions and usage reservations."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "011_voice_entitlements"
down_revision = "010_clerk_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_entitlements",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("external_subscription_id", sa.String(255), nullable=True),
        sa.Column("plan_code", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("included_seconds", sa.Integer(), nullable=False),
        sa.Column("reserved_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consumed_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("concurrency_limit", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_call_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("included_seconds >= 0", name="ck_voice_entitlement_included"),
        sa.CheckConstraint("reserved_seconds >= 0", name="ck_voice_entitlement_reserved"),
        sa.CheckConstraint("consumed_seconds >= 0", name="ck_voice_entitlement_consumed"),
        sa.CheckConstraint("concurrency_limit BETWEEN 1 AND 5", name="ck_voice_entitlement_concurrency"),
    )
    op.create_index("ix_voice_entitlements_status_period", "voice_entitlements", ["status", "period_end"])

    op.create_table(
        "voice_sessions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_session_id", pg.UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("provider_call_id", sa.String(255), nullable=True, unique=True),
        sa.Column("room_id", sa.String(255), nullable=True),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("language", sa.String(20), nullable=False),
        sa.Column("idempotency_key", pg.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("reserved_seconds", sa.Integer(), nullable=False),
        sa.Column("consumed_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consent_snapshot", sa.JSON(), nullable=False),
        sa.Column("source_mode", sa.String(40), nullable=False),
        sa.Column("trace_id", sa.String(80), nullable=False),
        sa.Column("error_category", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("reserved_seconds >= 0", name="ck_voice_session_reserved"),
        sa.CheckConstraint("consumed_seconds >= 0", name="ck_voice_session_consumed"),
    )
    op.create_index("ix_voice_sessions_owner_state", "voice_sessions", ["user_id", "state"])
    op.create_index("ix_voice_sessions_created_at", "voice_sessions", ["created_at"])

    op.create_table(
        "voice_usage_ledger",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("entitlement_id", pg.UUID(as_uuid=True), sa.ForeignKey("voice_entitlements.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("session_id", pg.UUID(as_uuid=True), sa.ForeignKey("voice_sessions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("entry_type", sa.String(30), nullable=False),
        sa.Column("seconds", sa.Integer(), nullable=False),
        sa.Column("settlement_reference", sa.String(255), nullable=False, unique=True),
        sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True),
        sa.Column("source_event_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_voice_ledger_entitlement_created", "voice_usage_ledger", ["entitlement_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_voice_ledger_entitlement_created", table_name="voice_usage_ledger")
    op.drop_table("voice_usage_ledger")
    op.drop_index("ix_voice_sessions_created_at", table_name="voice_sessions")
    op.drop_index("ix_voice_sessions_owner_state", table_name="voice_sessions")
    op.drop_table("voice_sessions")
    op.drop_index("ix_voice_entitlements_status_period", table_name="voice_entitlements")
    op.drop_table("voice_entitlements")
