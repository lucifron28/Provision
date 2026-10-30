import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from database_safety import create_owned_test_schema, drop_owned_test_schema


BACKEND_DIR = Path(__file__).resolve().parents[1]
EXPECTED_HEAD = "73ab14c6d982"


@pytest.fixture
def migration_schema(postgres_test_schema):
    owned = create_owned_test_schema(postgres_test_schema.database_url)
    try:
        yield owned
    finally:
        drop_owned_test_schema(owned)


def _run_alembic(owned_schema, *arguments):
    environment = os.environ.copy()
    environment["DATABASE_URL"] = owned_schema.database_url.render_as_string(
        hide_password=False
    )
    environment["PGOPTIONS"] = f"-c search_path={owned_schema.schema}"
    environment["JWT_SECRET_KEY"] = "migration-tests-only-secret"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=BACKEND_DIR,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"alembic {' '.join(arguments)} failed with {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return result


def _alembic_result(owned_schema, *arguments):
    environment = os.environ.copy()
    environment["DATABASE_URL"] = owned_schema.database_url.render_as_string(
        hide_password=False
    )
    environment["PGOPTIONS"] = f"-c search_path={owned_schema.schema}"
    environment["JWT_SECRET_KEY"] = "migration-tests-only-secret"
    return subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=BACKEND_DIR,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_postgresql18_migrations_upgrade_head_and_downgrade_base(migration_schema):
    engine = create_engine(migration_schema.scoped_url, pool_pre_ping=True)
    try:
        _run_alembic(migration_schema, "upgrade", "head")

        with engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert revision == EXPECTED_HEAD

        inspector = inspect(engine)
        table_names = set(inspector.get_table_names(schema=migration_schema.schema))
        assert {
            "users",
            "households",
            "household_memberships",
            "processing_consents",
            "food_preferences",
            "food_allergies",
            "ingredient_allergens",
            "ingredient_derivatives",
            "products",
            "storage_locations",
            "grocery_sessions",
            "inventory_batches",
            "shopping_list_items",
            "inventory_events",
            "alembic_version",
        } <= table_names

        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(DISTINCT allergen_code) FROM ingredient_allergens")).scalar_one() == 9
            assert connection.execute(text("""SELECT count(*) FROM ingredient_derivatives d
                JOIN ingredients c ON c.id=d.ingredient_id JOIN ingredients p ON p.id=d.parent_ingredient_id
                WHERE c.normalized_name='casein' AND p.normalized_name='milk' AND d.checked_at IS NOT NULL""")).scalar_one() == 1

        product_fk = next(
            fk
            for fk in inspector.get_foreign_keys(
                "inventory_batches", schema=migration_schema.schema
            )
            if fk["referred_table"] == "products"
        )
        assert product_fk["options"]["ondelete"] == "RESTRICT"
        event_fk = next(
            fk
            for fk in inspector.get_foreign_keys(
                "inventory_events", schema=migration_schema.schema
            )
            if fk["referred_table"] == "inventory_batches"
        )
        assert event_fk["options"]["ondelete"] == "RESTRICT"

        _run_alembic(migration_schema, "downgrade", "base")

        remaining_tables = set(inspect(engine).get_table_names(schema=migration_schema.schema))
        assert remaining_tables == {"alembic_version", "__provision_test_owner"}
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT count(*) FROM alembic_version")
            ).scalar_one() == 0
    finally:
        engine.dispose()


def test_household_downgrade_restores_legacy_foreign_keys(migration_schema):
    engine = create_engine(migration_schema.scoped_url, pool_pre_ping=True)
    try:
        _run_alembic(migration_schema, "upgrade", "head")
        _run_alembic(migration_schema, "downgrade", "a4d9c69b8f21")

        inspector = inspect(engine)
        expected = {
            "inventory_batches": {
                "fk_inventory_batches_product_id": ("products", ["product_id"], "RESTRICT"),
                "inventory_batches_storage_location_id_fkey": (
                    "storage_locations",
                    ["storage_location_id"],
                    "SET NULL",
                ),
                "inventory_batches_grocery_session_id_fkey": (
                    "grocery_sessions",
                    ["grocery_session_id"],
                    "SET NULL",
                ),
            },
            "shopping_list_items": {
                "shopping_list_items_product_id_fkey": (
                    "products",
                    ["product_id"],
                    "SET NULL",
                ),
            },
        }
        for table, foreign_keys in expected.items():
            actual = {
                fk["name"]: fk
                for fk in inspector.get_foreign_keys(table, schema=migration_schema.schema)
            }
            for name, (referred_table, columns, ondelete) in foreign_keys.items():
                fk = actual[name]
                assert fk["constrained_columns"] == columns
                assert fk["referred_table"] == referred_table
                assert fk["referred_columns"] == ["id"]
                assert fk["options"]["ondelete"] == ondelete

        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == "a4d9c69b8f21"
    finally:
        engine.dispose()


def test_downgrade_with_cross_household_duplicate_barcode_refuses_before_writes(
    migration_schema,
):
    engine = create_engine(migration_schema.scoped_url, pool_pre_ping=True)
    try:
        _run_alembic(migration_schema, "upgrade", "head")
        with engine.begin() as connection:
            quarantine_id = connection.execute(
                text("SELECT id FROM households WHERE slug = 'legacy-quarantine'")
            ).scalar_one()
            second_household_id = connection.execute(
                text(
                    "INSERT INTO households (name, slug) VALUES ('Second', 'second') "
                    "RETURNING id"
                )
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO products (household_id, name, barcode, source) "
                    "VALUES (:household_id, 'First', 'same-barcode', 'USER_CONFIRMED')"
                ),
                {"household_id": quarantine_id},
            )
            connection.execute(
                text(
                    "INSERT INTO products (household_id, name, barcode, source) "
                    "VALUES (:household_id, 'Second', 'same-barcode', 'USER_CONFIRMED')"
                ),
                {"household_id": second_household_id},
            )

        result = _alembic_result(migration_schema, "downgrade", "a4d9c69b8f21")
        assert result.returncode != 0
        assert "duplicate barcode values" in result.stderr

        inspector = inspect(engine)
        assert "household_id" in {
            column["name"]
            for column in inspector.get_columns("products", schema=migration_schema.schema)
        }
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == EXPECTED_HEAD
            assert connection.execute(
                text("SELECT count(*) FROM products WHERE barcode = 'same-barcode'")
            ).scalar_one() == 2
    finally:
        engine.dispose()
