import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from database_safety import create_owned_test_schema, drop_owned_test_schema


BACKEND_DIR = Path(__file__).resolve().parents[1]
EXPECTED_HEAD = "a4d9c69b8f21"


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
            "products",
            "storage_locations",
            "grocery_sessions",
            "inventory_batches",
            "shopping_list_items",
            "inventory_events",
            "alembic_version",
        } <= table_names

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
