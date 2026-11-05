"""Add identity bindings and consent versions without rewriting existing UUIDs."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "010_clerk_identity"
down_revision = "009_turn_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_identities",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("issuer", sa.String(500), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"),
                  nullable=False, unique=True),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("provider", "issuer", "subject", name="uq_auth_identity"),
    )
    op.create_table(
        "auth_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("details", pg.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.execute("CREATE TRIGGER auth_events_immutable BEFORE UPDATE OR DELETE ON auth_events "
               "FOR EACH ROW EXECUTE FUNCTION advisor_review_immutable()")
    op.add_column("consent_records", sa.Column("purpose_version", sa.String(40), nullable=False,
                                             server_default="legacy-v0"))


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM auth_identities) OR EXISTS (SELECT 1 FROM auth_events)
           OR EXISTS (SELECT 1 FROM consent_records WHERE purpose_version <> 'legacy-v0') THEN
            RAISE EXCEPTION 'Refusing downgrade while authentication records exist';
        END IF;
    END $$""")
    op.drop_column("consent_records", "purpose_version")
    op.drop_table("auth_events")
    op.drop_table("auth_identities")
