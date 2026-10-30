"""Add household ownership, membership, scoped product keys, and consent storage."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b83e6a7d4c91"
down_revision: Union[str, Sequence[str], None] = "a4d9c69b8f21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OWNED_TABLES = (
    "products",
    "storage_locations",
    "grocery_sessions",
    "inventory_batches",
    "shopping_list_items",
)


def _add_household_id(table: str) -> None:
    op.add_column(table, sa.Column("household_id", sa.Integer(), nullable=True))


def _drop_foreign_keys_to(table: str, referred_table: str) -> None:
    inspector = sa.inspect(op.get_bind())
    for foreign_key in inspector.get_foreign_keys(table):
        if foreign_key.get("referred_table") == referred_table and foreign_key.get("name"):
            op.drop_constraint(foreign_key["name"], table, type_="foreignkey")


def _assert_global_uniqueness_for_downgrade() -> None:
    bind = op.get_bind()
    checks = (
        ("products", "barcode", "barcode"),
        ("storage_locations", "name", "location name"),
        ("grocery_sessions", "idempotency_key", "idempotency key"),
    )
    for table, column, label in checks:
        duplicate = bind.execute(
            sa.text(
                f"SELECT {column} FROM {table} "
                f"WHERE {column} IS NOT NULL GROUP BY {column} HAVING count(*) > 1 LIMIT 1"
            )
        ).first()
        if duplicate:
            raise RuntimeError(
                f"Cannot downgrade household isolation without merging duplicate {label} values."
            )


def upgrade() -> None:
    op.create_table(
        "households",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_households_slug", "households", ["slug"], unique=True)

    op.create_table(
        "household_memberships",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role IN ('OWNER', 'MEMBER')", name="ck_household_membership_role"),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("household_id", "user_id", name="uq_household_membership_pair"),
    )
    op.create_index("ix_household_memberships_household_id", "household_memberships", ["household_id"])
    op.create_index("ix_household_memberships_user_id", "household_memberships", ["user_id"])
    op.create_index(
        "uq_household_memberships_user_default",
        "household_memberships",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_default IS TRUE"),
        sqlite_where=sa.text("is_default = 1"),
    )

    op.create_table(
        "processing_consents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=80), nullable=False),
        sa.Column("policy_version", sa.String(length=40), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "household_id", "user_id", "purpose", name="uq_processing_consent_scope"
        ),
    )
    op.create_index("ix_processing_consents_household_id", "processing_consents", ["household_id"])
    op.create_index("ix_processing_consents_user_id", "processing_consents", ["user_id"])

    for table in _OWNED_TABLES:
        _add_household_id(table)

    bind = op.get_bind()
    quarantine_id = bind.execute(
        sa.text(
            "INSERT INTO households (name, slug, created_at, updated_at) "
            "VALUES (:name, :slug, now(), now()) RETURNING id"
        ),
        {"name": "Legacy pantry quarantine", "slug": "legacy-quarantine"},
    ).scalar_one()
    for table in _OWNED_TABLES:
        bind.execute(
            sa.text(f"UPDATE {table} SET household_id = :household_id"),
            {"household_id": quarantine_id},
        )

    user_ids = bind.execute(sa.text("SELECT id FROM users ORDER BY id")).scalars().all()
    for user_id in user_ids:
        household_id = bind.execute(
            sa.text(
                "INSERT INTO households (name, slug, created_at, updated_at) "
                "VALUES (:name, :slug, now(), now()) RETURNING id"
            ),
            {"name": "Home", "slug": f"user-{user_id}"},
        ).scalar_one()
        bind.execute(
            sa.text(
                "INSERT INTO household_memberships "
                "(household_id, user_id, role, is_default, created_at, updated_at) "
                "VALUES (:household_id, :user_id, 'OWNER', true, now(), now())"
            ),
            {"household_id": household_id, "user_id": user_id},
        )

    for table in _OWNED_TABLES:
        op.alter_column(table, "household_id", existing_type=sa.Integer(), nullable=False)
        op.create_index(f"ix_{table}_household_id", table, ["household_id"])
        op.create_foreign_key(
            f"fk_{table}_household_id",
            table,
            "households",
            ["household_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    op.drop_index("ix_products_barcode", table_name="products")
    op.drop_index("ix_storage_locations_name", table_name="storage_locations")
    op.drop_index("ix_grocery_sessions_idempotency_key", table_name="grocery_sessions")

    op.create_unique_constraint("uq_products_household_id", "products", ["household_id", "id"])
    op.create_unique_constraint(
        "uq_products_household_barcode", "products", ["household_id", "barcode"]
    )
    op.create_unique_constraint(
        "uq_storage_locations_household_id", "storage_locations", ["household_id", "id"]
    )
    op.create_unique_constraint(
        "uq_storage_locations_household_name", "storage_locations", ["household_id", "name"]
    )
    op.create_unique_constraint(
        "uq_grocery_sessions_household_id", "grocery_sessions", ["household_id", "id"]
    )
    op.create_unique_constraint(
        "uq_grocery_sessions_household_idempotency_key",
        "grocery_sessions",
        ["household_id", "idempotency_key"],
    )
    op.create_unique_constraint(
        "uq_inventory_batches_household_id", "inventory_batches", ["household_id", "id"]
    )
    op.create_unique_constraint(
        "uq_shopping_items_household_id", "shopping_list_items", ["household_id", "id"]
    )

    _drop_foreign_keys_to("inventory_batches", "products")
    _drop_foreign_keys_to("inventory_batches", "storage_locations")
    _drop_foreign_keys_to("inventory_batches", "grocery_sessions")
    op.create_foreign_key(
        "fk_inventory_batches_household_product",
        "inventory_batches",
        "products",
        ["household_id", "product_id"],
        ["household_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_inventory_batches_household_location",
        "inventory_batches",
        "storage_locations",
        ["household_id", "storage_location_id"],
        ["household_id", "id"],
        ondelete="SET NULL (storage_location_id)",
    )
    op.create_foreign_key(
        "fk_inventory_batches_household_session",
        "inventory_batches",
        "grocery_sessions",
        ["household_id", "grocery_session_id"],
        ["household_id", "id"],
        ondelete="SET NULL (grocery_session_id)",
    )
    _drop_foreign_keys_to("shopping_list_items", "products")
    op.create_foreign_key(
        "fk_shopping_items_household_product",
        "shopping_list_items",
        "products",
        ["household_id", "product_id"],
        ["household_id", "id"],
        ondelete="SET NULL (product_id)",
    )


def downgrade() -> None:
    _assert_global_uniqueness_for_downgrade()

    op.drop_constraint(
        "fk_shopping_items_household_product", "shopping_list_items", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_inventory_batches_household_session", "inventory_batches", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_inventory_batches_household_location", "inventory_batches", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_inventory_batches_household_product", "inventory_batches", type_="foreignkey"
    )

    # Restore the pre-household referential actions before household_id disappears.
    # These names/options match the constraints at revision a4d9c69b8f21.
    op.create_foreign_key(
        "fk_inventory_batches_product_id",
        "inventory_batches",
        "products",
        ["product_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "inventory_batches_storage_location_id_fkey",
        "inventory_batches",
        "storage_locations",
        ["storage_location_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "inventory_batches_grocery_session_id_fkey",
        "inventory_batches",
        "grocery_sessions",
        ["grocery_session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "shopping_list_items_product_id_fkey",
        "shopping_list_items",
        "products",
        ["product_id"],
        ["id"],
        ondelete="SET NULL",
    )

    for constraint, table in (
        ("uq_shopping_items_household_id", "shopping_list_items"),
        ("uq_inventory_batches_household_id", "inventory_batches"),
        ("uq_grocery_sessions_household_idempotency_key", "grocery_sessions"),
        ("uq_grocery_sessions_household_id", "grocery_sessions"),
        ("uq_storage_locations_household_name", "storage_locations"),
        ("uq_storage_locations_household_id", "storage_locations"),
        ("uq_products_household_barcode", "products"),
        ("uq_products_household_id", "products"),
    ):
        op.drop_constraint(constraint, table, type_="unique")

    for table in _OWNED_TABLES:
        op.drop_constraint(f"fk_{table}_household_id", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_household_id", table_name=table)

    op.create_index("ix_products_barcode", "products", ["barcode"], unique=True)
    op.create_index("ix_storage_locations_name", "storage_locations", ["name"], unique=True)
    op.create_index(
        "ix_grocery_sessions_idempotency_key",
        "grocery_sessions",
        ["idempotency_key"],
        unique=True,
    )

    for table in reversed(_OWNED_TABLES):
        op.drop_column(table, "household_id")

    op.drop_index("ix_processing_consents_user_id", table_name="processing_consents")
    op.drop_index("ix_processing_consents_household_id", table_name="processing_consents")
    op.drop_table("processing_consents")
    op.drop_index("uq_household_memberships_user_default", table_name="household_memberships")
    op.drop_index("ix_household_memberships_user_id", table_name="household_memberships")
    op.drop_index("ix_household_memberships_household_id", table_name="household_memberships")
    op.drop_table("household_memberships")
    op.drop_index("ix_households_slug", table_name="households")
    op.drop_table("households")
