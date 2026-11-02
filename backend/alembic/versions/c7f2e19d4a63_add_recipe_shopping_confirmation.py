"""Add recipe-shopping revisions, provenance and idempotent confirmation."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c7f2e19d4a63"
down_revision = "aa812f04d937"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "households",
        sa.Column("shopping_revision", sa.BigInteger(), server_default="0", nullable=False),
    )
    op.add_column(
        "households",
        sa.Column("inventory_revision", sa.BigInteger(), server_default="0", nullable=False),
    )

    op.alter_column(
        "shopping_list_items",
        "quantity",
        existing_type=sa.Numeric(10, 2),
        type_=sa.Numeric(14, 6),
        existing_nullable=False,
    )
    op.add_column(
        "shopping_list_items",
        sa.Column("ingredient_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "shopping_list_items",
        sa.Column("origin_recipe_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "shopping_list_items",
        sa.Column("origin_recipe_revision", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_shopping_list_items_ingredient_id", "shopping_list_items", ["ingredient_id"]
    )
    op.create_index(
        "ix_shopping_list_items_origin_recipe_id", "shopping_list_items", ["origin_recipe_id"]
    )
    op.create_foreign_key(
        "fk_shopping_list_items_ingredient",
        "shopping_list_items",
        "ingredients",
        ["ingredient_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_shopping_items_household_recipe_revision",
        "shopping_list_items",
        "recipe_revisions",
        ["household_id", "origin_recipe_id", "origin_recipe_revision"],
        ["household_id", "recipe_id", "revision"],
        ondelete="SET NULL (origin_recipe_id, origin_recipe_revision)",
    )
    op.create_check_constraint(
        "ck_shopping_items_origin_recipe_pair",
        "shopping_list_items",
        "(origin_recipe_id IS NULL AND origin_recipe_revision IS NULL) OR "
        "(origin_recipe_id IS NOT NULL AND origin_recipe_revision IS NOT NULL)",
    )

    op.create_table(
        "recipe_shopping_idempotency",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(idempotency_key) BETWEEN 8 AND 128", name="ck_recipe_shopping_key_length"),
        sa.CheckConstraint("length(request_hash) = 64", name="ck_recipe_shopping_request_hash"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("household_id", "idempotency_key", name="uq_recipe_shopping_household_key"),
    )
    op.create_index(
        "ix_recipe_shopping_idempotency_household_id",
        "recipe_shopping_idempotency",
        ["household_id"],
    )


def _assert_downgrade_preserves_data() -> None:
    bind = op.get_bind()
    precision_loss = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM shopping_list_items "
            "WHERE quantity <> round(quantity, 2) "
            "OR quantity > 99999999.99 OR quantity < -99999999.99)"
        )
    ).scalar_one()
    if precision_loss:
        raise RuntimeError("Cannot downgrade shopping quantities: values exceed Numeric(10,2) precision")

    metadata_loss = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM shopping_list_items "
            "WHERE ingredient_id IS NOT NULL OR origin_recipe_id IS NOT NULL "
            "OR origin_recipe_revision IS NOT NULL)"
        )
    ).scalar_one()
    idempotency_loss = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM recipe_shopping_idempotency)")
    ).scalar_one()
    revision_loss = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM households "
            "WHERE shopping_revision <> 0 OR inventory_revision <> 0)"
        )
    ).scalar_one()
    if metadata_loss or idempotency_loss or revision_loss:
        raise RuntimeError("Cannot downgrade: recipe-shopping metadata, retry records, or revisions would be lost")


def downgrade() -> None:
    _assert_downgrade_preserves_data()

    op.drop_index(
        "ix_recipe_shopping_idempotency_household_id", table_name="recipe_shopping_idempotency"
    )
    op.drop_table("recipe_shopping_idempotency")

    op.drop_constraint(
        "ck_shopping_items_origin_recipe_pair", "shopping_list_items", type_="check"
    )
    op.drop_constraint(
        "fk_shopping_items_household_recipe_revision", "shopping_list_items", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_shopping_list_items_ingredient", "shopping_list_items", type_="foreignkey"
    )
    op.drop_index("ix_shopping_list_items_origin_recipe_id", table_name="shopping_list_items")
    op.drop_index("ix_shopping_list_items_ingredient_id", table_name="shopping_list_items")
    op.drop_column("shopping_list_items", "origin_recipe_revision")
    op.drop_column("shopping_list_items", "origin_recipe_id")
    op.drop_column("shopping_list_items", "ingredient_id")
    op.alter_column(
        "shopping_list_items",
        "quantity",
        existing_type=sa.Numeric(14, 6),
        type_=sa.Numeric(10, 2),
        existing_nullable=False,
    )
    op.drop_column("households", "inventory_revision")
    op.drop_column("households", "shopping_revision")
