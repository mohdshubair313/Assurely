"""006: immutable, unit-preserving reviewed records inside policy_terms."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "006_reviewed_policy_terms"
down_revision = "005_policy_publication"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "policy_terms",
        sa.Column("record_kind", sa.String(20), nullable=False, server_default="legacy"),
    )
    op.add_column("policy_terms", sa.Column("publication_digest", sa.String(64), nullable=True))
    op.add_column("policy_terms", sa.Column("reviewed_facts_json", pg.JSONB, nullable=True))
    op.alter_column("policy_terms", "policy_document_id", nullable=True)
    op.alter_column("policy_terms", "effective_date", nullable=True)
    op.create_foreign_key(
        "fk_policy_terms_publication",
        "policy_terms",
        "policy_publications",
        ["publication_digest"],
        ["digest"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_policy_terms_publication", "policy_terms", ["publication_digest"]
    )
    op.create_check_constraint(
        "ck_policy_terms_record_kind",
        "policy_terms",
        "(record_kind = 'legacy' AND policy_document_id IS NOT NULL "
        "AND effective_date IS NOT NULL AND publication_digest IS NULL "
        "AND reviewed_facts_json IS NULL) OR "
        "(record_kind = 'reviewed_v1' AND policy_document_id IS NULL "
        "AND effective_date IS NULL AND expiry_date IS NULL AND publication_digest IS NOT NULL "
        "AND version_hash = publication_digest AND reviewed_facts_json IS NOT NULL "
        "AND sum_insured_min IS NULL AND sum_insured_max IS NULL "
        "AND entry_age_min IS NULL AND entry_age_max IS NULL "
        "AND waiting_period_days_preexisting IS NULL AND exclusions_json IS NULL "
        "AND premium_rate_table_json IS NULL)",
    )
    op.execute("""
        CREATE FUNCTION policy_terms_reviewed_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.record_kind = 'reviewed_v1' THEN
                RAISE EXCEPTION 'Reviewed policy terms are append-only';
            END IF;
            IF TG_OP = 'UPDATE' AND NEW.record_kind = 'reviewed_v1' THEN
                RAISE EXCEPTION 'Reviewed policy terms must be inserted';
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute(
        "CREATE TRIGGER reviewed_terms_immutable BEFORE UPDATE OR DELETE ON policy_terms "
        "FOR EACH ROW EXECUTE FUNCTION policy_terms_reviewed_immutable()"
    )


def downgrade() -> None:
    # Dropping these columns with reviewed rows would destroy audit evidence.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM policy_terms WHERE record_kind = 'reviewed_v1') THEN
                RAISE EXCEPTION 'Refusing downgrade while reviewed policy terms exist';
            END IF;
        END $$
    """)
    op.execute("DROP TRIGGER reviewed_terms_immutable ON policy_terms")
    op.execute("DROP FUNCTION policy_terms_reviewed_immutable()")
    op.drop_constraint("ck_policy_terms_record_kind", "policy_terms", type_="check")
    op.drop_constraint("uq_policy_terms_publication", "policy_terms", type_="unique")
    op.drop_constraint("fk_policy_terms_publication", "policy_terms", type_="foreignkey")
    op.alter_column("policy_terms", "effective_date", nullable=False)
    op.alter_column("policy_terms", "policy_document_id", nullable=False)
    op.drop_column("policy_terms", "reviewed_facts_json")
    op.drop_column("policy_terms", "publication_digest")
    op.drop_column("policy_terms", "record_kind")
