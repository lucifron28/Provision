"""Add household weekly plans, history and shopping provenance."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "d84b3c6a19e2"
down_revision = "c7f2e19d4a63"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meal_plans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("revision > 0", name="ck_meal_plans_revision"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("household_id", "id", name="uq_meal_plans_household_id"),
        sa.UniqueConstraint("household_id", "week_start", name="uq_meal_plans_household_week"),
    )
    op.create_index("ix_meal_plans_household_id", "meal_plans", ["household_id"])

    op.create_table(
        "meal_plan_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("meal_date", sa.Date(), nullable=False),
        sa.Column("slot", sa.String(length=16), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("recipe_id", sa.Integer(), nullable=False),
        sa.Column("recipe_revision", sa.Integer(), nullable=False),
        sa.Column("servings", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.CheckConstraint(
            "slot IN ('breakfast', 'lunch', 'dinner', 'merienda')",
            name="ck_meal_plan_entry_slot",
        ),
        sa.CheckConstraint("position BETWEEN 0 AND 9", name="ck_meal_plan_entry_position"),
        sa.CheckConstraint("servings > 0", name="ck_meal_plan_entry_servings"),
        sa.ForeignKeyConstraint(
            ["household_id", "plan_id"],
            ["meal_plans.household_id", "meal_plans.id"],
            name="fk_meal_plan_entry_household_plan",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["household_id", "recipe_id", "recipe_revision"],
            ["recipe_revisions.household_id", "recipe_revisions.recipe_id", "recipe_revisions.revision"],
            name="fk_meal_plan_entry_recipe_revision",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("household_id", "id", name="uq_meal_plan_entries_household_id"),
        sa.UniqueConstraint(
            "household_id", "plan_id", "meal_date", "slot", "position",
            name="uq_meal_plan_entry_slot_position",
        ),
    )
    op.create_index("ix_meal_plan_entries_household_id", "meal_plan_entries", ["household_id"])
    op.create_index("ix_meal_plan_entries_plan_id", "meal_plan_entries", ["plan_id"])
    op.create_index("ix_meal_plan_entries_recipe_id", "meal_plan_entries", ["recipe_id"])

    op.create_table(
        "meal_plan_revisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("revision > 0", name="ck_meal_plan_revision_revision"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["household_id", "plan_id"],
            ["meal_plans.household_id", "meal_plans.id"],
            name="fk_meal_plan_revision_household_plan",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("household_id", "plan_id", "revision", name="uq_meal_plan_revision"),
    )
    op.create_index("ix_meal_plan_revisions_household_id", "meal_plan_revisions", ["household_id"])
    op.create_index("ix_meal_plan_revisions_plan_id", "meal_plan_revisions", ["plan_id"])

    op.add_column("shopping_list_items", sa.Column("origin_plan_id", sa.Integer(), nullable=True))
    op.add_column(
        "shopping_list_items", sa.Column("origin_plan_revision", sa.Integer(), nullable=True)
    )
    op.create_index(
        "ix_shopping_list_items_origin_plan_id", "shopping_list_items", ["origin_plan_id"]
    )
    op.create_foreign_key(
        "fk_shopping_items_household_plan_revision",
        "shopping_list_items",
        "meal_plan_revisions",
        ["household_id", "origin_plan_id", "origin_plan_revision"],
        ["household_id", "plan_id", "revision"],
        ondelete="SET NULL (origin_plan_id, origin_plan_revision)",
    )
    op.create_check_constraint(
        "ck_shopping_items_origin_plan_pair",
        "shopping_list_items",
        "(origin_plan_id IS NULL AND origin_plan_revision IS NULL) OR "
        "(origin_plan_id IS NOT NULL AND origin_plan_revision IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_shopping_items_single_origin",
        "shopping_list_items",
        "origin_recipe_id IS NULL OR origin_plan_id IS NULL",
    )


def _assert_downgrade_preserves_data() -> None:
    bind = op.get_bind()
    plans_exist = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM meal_plans) "
            "OR EXISTS (SELECT 1 FROM meal_plan_entries) "
            "OR EXISTS (SELECT 1 FROM meal_plan_revisions)"
        )
    ).scalar_one()
    shopping_provenance_exists = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM shopping_list_items "
            "WHERE origin_plan_id IS NOT NULL OR origin_plan_revision IS NOT NULL)"
        )
    ).scalar_one()
    if plans_exist or shopping_provenance_exists:
        raise RuntimeError("Cannot downgrade: meal plans, history, or shopping provenance would be lost")


def downgrade() -> None:
    _assert_downgrade_preserves_data()

    op.drop_constraint(
        "ck_shopping_items_single_origin", "shopping_list_items", type_="check"
    )
    op.drop_constraint(
        "ck_shopping_items_origin_plan_pair", "shopping_list_items", type_="check"
    )
    op.drop_constraint(
        "fk_shopping_items_household_plan_revision", "shopping_list_items", type_="foreignkey"
    )
    op.drop_index("ix_shopping_list_items_origin_plan_id", table_name="shopping_list_items")
    op.drop_column("shopping_list_items", "origin_plan_revision")
    op.drop_column("shopping_list_items", "origin_plan_id")

    op.drop_index("ix_meal_plan_revisions_plan_id", table_name="meal_plan_revisions")
    op.drop_index("ix_meal_plan_revisions_household_id", table_name="meal_plan_revisions")
    op.drop_table("meal_plan_revisions")
    op.drop_index("ix_meal_plan_entries_recipe_id", table_name="meal_plan_entries")
    op.drop_index("ix_meal_plan_entries_plan_id", table_name="meal_plan_entries")
    op.drop_index("ix_meal_plan_entries_household_id", table_name="meal_plan_entries")
    op.drop_table("meal_plan_entries")
    op.drop_index("ix_meal_plans_household_id", table_name="meal_plans")
    op.drop_table("meal_plans")
