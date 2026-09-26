"""001 — Initial schema.

Creates all tables from the LLD § 7.4 Postgres schema:
  users, consent_records, sessions, audit_log, escalations,
  policy_documents, policy_terms, decision_trace.

Revision ID: 001_initial_schema
Revises: (none)
Create Date: 2026-09-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── users ──────────────────────────────────────────────────────────
    # role: customer | advisor | admin
    # tenant_id: nullable, reserved for future white-label broker partners
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("phone_hash", sa.String(128), nullable=True, unique=True),
        sa.Column("email_hash", sa.String(128), nullable=True, unique=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="customer"),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_users_role", "users", ["role"])

    # ── consent_records ────────────────────────────────────────────────
    op.create_table(
        "consent_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope", sa.String(100), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_consent_records_user_id", "consent_records", ["user_id"])

    # ── sessions ───────────────────────────────────────────────────────
    op.create_table(
        "sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("intent", sa.String(20), nullable=True),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    # ── audit_log ──────────────────────────────────────────────────────
    op.create_table(
        "audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_name", sa.String(50), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("output_hash", sa.String(64), nullable=False),
        sa.Column("sources_json", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_audit_log_session_id", "audit_log", ["session_id"])
    op.create_index("ix_audit_log_node_name", "audit_log", ["node_name"])

    # ── escalations ────────────────────────────────────────────────────
    op.create_table(
        "escalations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("assigned_advisor", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_escalations_session_id", "escalations", ["session_id"])
    op.create_index("ix_escalations_status", "escalations", ["status"])

    # ── policy_documents ───────────────────────────────────────────────
    op.create_table(
        "policy_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("insurer", sa.String(200), nullable=False),
        sa.Column("product_name", sa.String(200), nullable=False),
        sa.Column("doc_url", sa.Text, nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("version_hash", sa.String(64), nullable=False),
    )
    op.create_index("ix_policy_documents_insurer", "policy_documents", ["insurer"])

    # ── policy_terms ───────────────────────────────────────────────────
    # Structured, versioned, queried deterministically — never inferred by an LLM.
    # RAG stays reserved for clause wording and explanations, not numbers or eligibility.
    op.create_table(
        "policy_terms",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("policy_document_id", UUID(as_uuid=True), sa.ForeignKey("policy_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_hash", sa.String(64), nullable=False),
        sa.Column("sum_insured_min", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("sum_insured_max", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("entry_age_min", sa.Integer, nullable=True),
        sa.Column("entry_age_max", sa.Integer, nullable=True),
        sa.Column("waiting_period_days_preexisting", sa.Integer, nullable=True),
        sa.Column("exclusions_json", JSONB, nullable=True),
        sa.Column("premium_rate_table_json", JSONB, nullable=True),
        sa.Column("effective_date", sa.Date, nullable=False),
        sa.Column("expiry_date", sa.Date, nullable=True),
    )
    op.create_index("ix_policy_terms_policy_document_id", "policy_terms", ["policy_document_id"])
    op.create_index("ix_policy_terms_effective_date", "policy_terms", ["effective_date"])

    # ── decision_trace ─────────────────────────────────────────────────
    # One row per recommendation. Answers "why did it say that" without
    # reconstructing from logs. Supports replay-and-diff for regression detection.
    op.create_table(
        "decision_trace",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_profile_snapshot_json", JSONB, nullable=False),
        sa.Column("policy_versions_evaluated_json", JSONB, nullable=False),
        sa.Column("clauses_retrieved_json", JSONB, nullable=True),
        sa.Column("rules_engine_output_json", JSONB, nullable=True),
        sa.Column("sources_per_claim_json", JSONB, nullable=True),
        sa.Column("model_version", sa.String(100), nullable=True),
        sa.Column("prompt_version", sa.String(100), nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column("confidence_inputs_json", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_decision_trace_session_id", "decision_trace", ["session_id"])


def downgrade() -> None:
    op.drop_table("decision_trace")
    op.drop_table("policy_terms")
    op.drop_table("policy_documents")
    op.drop_table("escalations")
    op.drop_table("audit_log")
    op.drop_table("sessions")
    op.drop_table("consent_records")
    op.drop_table("users")
