"""Add recorded cooking sessions and household leftovers."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f19c02a6e4b7"
down_revision = "d84b3c6a19e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cooking_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("recipe_id", sa.Integer(), nullable=False),
        sa.Column("recipe_revision", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("servings", sa.Numeric(12, 4), nullable=False),
        sa.Column("inventory_revision", sa.BigInteger(), nullable=False),
        sa.Column("source_reference_id", sa.Integer(), nullable=True),
        sa.Column("source_reference_revision", sa.Integer(), nullable=True),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("source_revision", sa.Integer(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("recipe_revision > 0", name="ck_cooking_session_recipe_revision"),
        sa.CheckConstraint("servings > 0", name="ck_cooking_session_servings"),
        sa.CheckConstraint(
            "source_reference_revision IS NULL OR source_reference_revision > 0",
            name="ck_cooking_session_source_reference_revision",
        ),
        sa.CheckConstraint(
            "source_revision IS NULL OR source_revision > 0",
            name="ck_cooking_session_source_revision",
        ),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["source_reference_id"], ["recipe_source_references.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["source_id"], ["recipe_sources.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["household_id", "recipe_id", "recipe_revision"],
            ["recipe_revisions.household_id", "recipe_revisions.recipe_id", "recipe_revisions.revision"],
            name="fk_cooking_session_recipe_revision",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("household_id", "id", name="uq_cooking_sessions_household_id"),
    )
    op.create_index("ix_cooking_sessions_household_id", "cooking_sessions", ["household_id"])
    op.create_index("ix_cooking_sessions_actor_user_id", "cooking_sessions", ["actor_user_id"])

    op.create_table(
        "cooking_consumptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("cooking_session_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("inventory_event_id", sa.Integer(), nullable=False),
        sa.Column("ingredient_id", sa.Integer(), nullable=False),
        sa.Column("ingredient_quantity", sa.Numeric(14, 6), nullable=False),
        sa.Column("ingredient_unit", sa.String(length=24), nullable=False),
        sa.CheckConstraint("ingredient_quantity > 0", name="ck_cooking_consumption_quantity"),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["household_id", "cooking_session_id"],
            ["cooking_sessions.household_id", "cooking_sessions.id"],
            name="fk_cooking_consumption_session",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["household_id", "batch_id"],
            ["inventory_batches.household_id", "inventory_batches.id"],
            name="fk_cooking_consumption_batch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["inventory_event_id"], ["inventory_events.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredients.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "household_id", "cooking_session_id", "batch_id",
            name="uq_cooking_consumption_session_batch",
        ),
        sa.UniqueConstraint("inventory_event_id", name="uq_cooking_consumption_inventory_event"),
    )
    op.create_index("ix_cooking_consumptions_household_id", "cooking_consumptions", ["household_id"])
    op.create_index("ix_cooking_consumptions_batch_id", "cooking_consumptions", ["batch_id"])
    op.create_index("ix_cooking_consumptions_ingredient_id", "cooking_consumptions", ["ingredient_id"])

    op.create_table(
        "cooking_idempotency",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("cooking_session_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "length(idempotency_key) BETWEEN 8 AND 128",
            name="ck_cooking_idempotency_key_length",
        ),
        sa.CheckConstraint("length(request_hash) = 64", name="ck_cooking_idempotency_hash"),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["household_id", "cooking_session_id"],
            ["cooking_sessions.household_id", "cooking_sessions.id"],
            name="fk_cooking_idempotency_session",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "household_id", "idempotency_key", name="uq_cooking_idempotency_household_key"
        ),
    )
    op.create_index("ix_cooking_idempotency_household_id", "cooking_idempotency", ["household_id"])

    op.create_table(
        "leftovers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("recipe_id", sa.Integer(), nullable=True),
        sa.Column("recipe_revision", sa.Integer(), nullable=True),
        sa.Column("cooking_session_id", sa.Integer(), nullable=True),
        sa.Column("storage_location_id", sa.Integer(), nullable=True),
        sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("use_by_date", sa.Date(), nullable=True),
        sa.Column("use_by_date_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 6), nullable=False),
        sa.Column("remaining_quantity", sa.Numeric(14, 6), nullable=False),
        sa.Column("unit", sa.String(length=24), nullable=False),
        sa.Column("portions", sa.Numeric(12, 4), nullable=True),
        sa.Column("remaining_portions", sa.Numeric(12, 4), nullable=True),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "(recipe_id IS NULL AND recipe_revision IS NULL) OR "
            "(recipe_id IS NOT NULL AND recipe_revision IS NOT NULL)",
            name="ck_leftovers_recipe_revision_pair",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_leftovers_quantity_positive"),
        sa.CheckConstraint(
            "remaining_quantity >= 0 AND remaining_quantity <= quantity",
            name="ck_leftovers_remaining_quantity",
        ),
        sa.CheckConstraint(
            "(portions IS NULL AND remaining_portions IS NULL) OR "
            "(portions IS NOT NULL AND remaining_portions IS NOT NULL AND "
            "portions > 0 AND remaining_portions >= 0 AND remaining_portions <= portions)",
            name="ck_leftovers_remaining_portions",
        ),
        sa.CheckConstraint(
            "(use_by_date IS NULL AND use_by_date_verified IS FALSE) OR "
            "(use_by_date IS NOT NULL AND use_by_date_verified IS TRUE)",
            name="ck_leftovers_use_by_verification",
        ),
        sa.CheckConstraint("revision > 0", name="ck_leftovers_revision"),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["household_id", "storage_location_id"],
            ["storage_locations.household_id", "storage_locations.id"],
            name="fk_leftovers_household_location",
            ondelete="SET NULL (storage_location_id)",
        ),
        sa.ForeignKeyConstraint(
            ["household_id", "recipe_id", "recipe_revision"],
            ["recipe_revisions.household_id", "recipe_revisions.recipe_id", "recipe_revisions.revision"],
            name="fk_leftovers_recipe_revision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["household_id", "cooking_session_id"],
            ["cooking_sessions.household_id", "cooking_sessions.id"],
            name="fk_leftovers_cooking_session",
            ondelete="SET NULL (cooking_session_id)",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("household_id", "id", name="uq_leftovers_household_id"),
    )
    op.create_index("ix_leftovers_household_id", "leftovers", ["household_id"])
    op.create_index("ix_leftovers_cooking_session_id", "leftovers", ["cooking_session_id"])
    op.create_index("ix_leftovers_storage_location_id", "leftovers", ["storage_location_id"])

    op.create_table(
        "leftover_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("leftover_id", sa.Integer(), nullable=False),
        sa.Column("cooking_session_id", sa.Integer(), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 6), nullable=False),
        sa.Column("unit", sa.String(length=24), nullable=False),
        sa.Column("portions", sa.Numeric(12, 4), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.CheckConstraint("event_type IN ('CONSUMED', 'DISCARDED')", name="ck_leftover_event_type"),
        sa.CheckConstraint("quantity > 0", name="ck_leftover_event_quantity"),
        sa.CheckConstraint("portions IS NULL OR portions > 0", name="ck_leftover_event_portions"),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["household_id", "leftover_id"],
            ["leftovers.household_id", "leftovers.id"],
            name="fk_leftover_events_household_leftover",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["household_id", "cooking_session_id"],
            ["cooking_sessions.household_id", "cooking_sessions.id"],
            name="fk_leftover_events_cooking_session",
            ondelete="SET NULL (cooking_session_id)",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_leftover_events_household_id", "leftover_events", ["household_id"])
    op.create_index("ix_leftover_events_leftover_id", "leftover_events", ["leftover_id"])


def _assert_downgrade_preserves_data() -> None:
    bind = op.get_bind()
    data_exists = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM cooking_sessions) "
            "OR EXISTS (SELECT 1 FROM cooking_consumptions) "
            "OR EXISTS (SELECT 1 FROM cooking_idempotency) "
            "OR EXISTS (SELECT 1 FROM leftovers) "
            "OR EXISTS (SELECT 1 FROM leftover_events)"
        )
    ).scalar_one()
    if data_exists:
        raise RuntimeError("Cannot downgrade: cooking or leftover history would be lost")


def downgrade() -> None:
    _assert_downgrade_preserves_data()
    op.drop_index("ix_leftover_events_leftover_id", table_name="leftover_events")
    op.drop_index("ix_leftover_events_household_id", table_name="leftover_events")
    op.drop_table("leftover_events")
    op.drop_index("ix_leftovers_storage_location_id", table_name="leftovers")
    op.drop_index("ix_leftovers_cooking_session_id", table_name="leftovers")
    op.drop_index("ix_leftovers_household_id", table_name="leftovers")
    op.drop_table("leftovers")
    op.drop_index("ix_cooking_idempotency_household_id", table_name="cooking_idempotency")
    op.drop_table("cooking_idempotency")
    op.drop_index("ix_cooking_consumptions_ingredient_id", table_name="cooking_consumptions")
    op.drop_index("ix_cooking_consumptions_batch_id", table_name="cooking_consumptions")
    op.drop_index("ix_cooking_consumptions_household_id", table_name="cooking_consumptions")
    op.drop_table("cooking_consumptions")
    op.drop_index("ix_cooking_sessions_actor_user_id", table_name="cooking_sessions")
    op.drop_index("ix_cooking_sessions_household_id", table_name="cooking_sessions")
    op.drop_table("cooking_sessions")
