"""Add private member and shared household food profiles."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "f62c910e7a43"
down_revision = "d91e84af0c52"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("food_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("household_id", sa.Integer(), sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("member_user_id", sa.Integer(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("preferences", postgresql.JSONB(), nullable=False),
        sa.Column("allergy_status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["household_id", "member_user_id"],
            ["household_memberships.household_id", "household_memberships.user_id"],
            ondelete="CASCADE", name="fk_food_preferences_membership"),
        sa.CheckConstraint("revision > 0", name="ck_food_preferences_revision"),
        sa.CheckConstraint("allergy_status IN ('NOT_PROVIDED', 'NONE_DECLARED', 'DECLARED')",
            name="ck_food_preferences_allergy_status"))
    op.create_index("uq_food_preferences_member", "food_preferences", ["household_id", "member_user_id"],
        unique=True, postgresql_where=sa.text("member_user_id IS NOT NULL"))
    op.create_index("uq_food_preferences_household", "food_preferences", ["household_id"],
        unique=True, postgresql_where=sa.text("member_user_id IS NULL"))
    op.create_table("food_allergies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("food_preferences.id", ondelete="CASCADE"), nullable=False),
        sa.Column("allergen_code", sa.String(32), nullable=True),
        sa.Column("custom_text", sa.String(180), nullable=True),
        sa.Column("severity", sa.String(16), nullable=True),
        sa.Column("cross_contact_concern", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint("(allergen_code IS NOT NULL) <> (custom_text IS NOT NULL)", name="ck_food_allergies_reference"))
    op.create_index("ix_food_allergies_profile_id", "food_allergies", ["profile_id"])


def downgrade():
    op.drop_table("food_allergies")
    op.drop_table("food_preferences")
