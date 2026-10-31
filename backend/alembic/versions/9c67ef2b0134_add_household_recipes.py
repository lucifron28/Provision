"""Add household recipes, immutable revisions and private bookmarks."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "9c67ef2b0134"
down_revision = "821de4cb7a36"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("recipes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("household_id", sa.Integer(), sa.ForeignKey("households.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("cuisine", sa.String(80), nullable=False),
        sa.Column("content", JSONB(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("household_id", "id", name="uq_recipes_household_id"),
        sa.CheckConstraint("revision > 0", name="ck_recipes_revision"))
    op.create_index("ix_recipes_household_id", "recipes", ["household_id"])
    op.create_table("recipe_ingredients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("recipe_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("ingredient_id", sa.Integer(), sa.ForeignKey("ingredients.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("display_name", sa.String(180), nullable=False),
        sa.Column("amount", sa.Numeric(14, 6), nullable=False),
        sa.Column("unit", sa.String(50), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("preparation", sa.String(500), nullable=True),
        sa.Column("substitution_options", JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["household_id", "recipe_id"], ["recipes.household_id", "recipes.id"],
            name="fk_recipe_ingredient_household", ondelete="CASCADE"),
        sa.UniqueConstraint("household_id", "recipe_id", "position", name="uq_recipe_ingredient_position"),
        sa.CheckConstraint("amount > 0", name="ck_recipe_ingredient_amount"))
    op.create_table("recipe_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("recipe_id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["household_id", "recipe_id"], ["recipes.household_id", "recipes.id"],
            name="fk_recipe_revision_household", ondelete="CASCADE"),
        sa.UniqueConstraint("household_id", "recipe_id", "revision", name="uq_recipe_revision"))
    op.create_table("saved_recipes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("member_user_id", sa.Integer(), nullable=False),
        sa.Column("recipe_id", sa.Integer(), nullable=False),
        sa.Column("recipe_revision", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("is_saved", sa.Boolean(), nullable=False),
        sa.Column("favorite", sa.Boolean(), nullable=False),
        sa.Column("servings", sa.Numeric(12, 4), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["household_id", "member_user_id"],
            ["household_memberships.household_id", "household_memberships.user_id"],
            name="fk_saved_recipe_membership", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["household_id", "recipe_id", "recipe_revision"],
            ["recipe_revisions.household_id", "recipe_revisions.recipe_id", "recipe_revisions.revision"],
            name="fk_saved_recipe_revision", ondelete="CASCADE"),
        sa.UniqueConstraint("household_id", "member_user_id", "recipe_id", name="uq_saved_recipe_member"),
        sa.CheckConstraint("revision > 0", name="ck_saved_recipe_revision"))


def downgrade():
    op.drop_table("saved_recipes")
    op.drop_table("recipe_revisions")
    op.drop_table("recipe_ingredients")
    op.drop_table("recipes")
