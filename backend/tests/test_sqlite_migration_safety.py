import os
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from app.models.household import Household, HouseholdMembership, HouseholdRole
from app.models.batch import InventoryBatch
from app.models.event import EventType, InventoryEvent
from app.models.location import StorageLocation
from app.models.product import Product, ProductSource
from app.models.session import GrocerySession, GrocerySessionStatus
from app.models.shopping import ShoppingListItem
from app.models.user import User
from app.models.household import Household, HouseholdRole
from database_safety import (
    create_owned_test_schema,
    drop_owned_test_schema,
    test_schema_without_owner_marker as schema_without_owner_marker,
)
from scripts.migrate_sqlite_to_postgres import (
    TABLES_IN_DEPENDENCY_ORDER,
    create_sqlite_backup,
    get_postgres_table_counts,
    main,
    migrate_data,
)


BACKEND_DIR = Path(__file__).resolve().parents[1]


def _sqlite_url(path):
    return URL.create("sqlite", database=str(path))


def create_legacy_database(path):
    purchased_at = datetime(2026, 10, 30, 8, 45, 12, tzinfo=timezone.utc)
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                hashed_password VARCHAR(255) NOT NULL,
                display_name VARCHAR(100),
                is_active BOOLEAN NOT NULL DEFAULT 1,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE UNIQUE INDEX ix_users_email ON users (email);
            CREATE TABLE grocery_sessions (
                id INTEGER PRIMARY KEY,
                store_name VARCHAR(255) NOT NULL,
                purchase_date DATETIME NOT NULL,
                total_amount NUMERIC(10, 2),
                status VARCHAR(9) NOT NULL,
                notes TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                idempotency_key VARCHAR(36),
                idempotency_fingerprint VARCHAR(64)
            );
            CREATE UNIQUE INDEX ix_grocery_sessions_idempotency_key
                ON grocery_sessions (idempotency_key);
            CREATE TABLE products (
                id INTEGER PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                brand VARCHAR(255),
                barcode VARCHAR(100),
                category VARCHAR(100),
                package_size FLOAT,
                unit VARCHAR(50),
                image_url VARCHAR(500),
                source VARCHAR(20) NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE UNIQUE INDEX ix_products_barcode ON products (barcode);
            CREATE INDEX ix_products_category ON products (category);
            CREATE INDEX ix_products_name ON products (name);
            CREATE TABLE storage_locations (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE UNIQUE INDEX ix_storage_locations_name ON storage_locations (name);
            CREATE TABLE inventory_batches (
                id INTEGER PRIMARY KEY,
                product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                storage_location_id INTEGER REFERENCES storage_locations(id) ON DELETE SET NULL,
                grocery_session_id INTEGER REFERENCES grocery_sessions(id) ON DELETE SET NULL,
                purchased_at DATETIME NOT NULL,
                expiration_date DATE,
                original_quantity NUMERIC(10, 2) NOT NULL,
                remaining_quantity NUMERIC(10, 2) NOT NULL,
                unit_price NUMERIC(10, 2),
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX ix_inventory_batches_expiration_date ON inventory_batches (expiration_date);
            CREATE INDEX ix_inventory_batches_grocery_session_id ON inventory_batches (grocery_session_id);
            CREATE INDEX ix_inventory_batches_product_id ON inventory_batches (product_id);
            CREATE INDEX ix_inventory_batches_remaining_quantity ON inventory_batches (remaining_quantity);
            CREATE INDEX ix_inventory_batches_storage_location_id ON inventory_batches (storage_location_id);
            CREATE TABLE shopping_list_items (
                id INTEGER PRIMARY KEY,
                product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
                name VARCHAR(255) NOT NULL,
                quantity NUMERIC(10, 2) NOT NULL,
                unit VARCHAR(50),
                is_bought BOOLEAN NOT NULL,
                notes TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX ix_shopping_list_items_is_bought ON shopping_list_items (is_bought);
            CREATE INDEX ix_shopping_list_items_product_id ON shopping_list_items (product_id);
            CREATE TABLE inventory_events (
                id INTEGER PRIMARY KEY,
                batch_id INTEGER NOT NULL REFERENCES inventory_batches(id) ON DELETE CASCADE,
                event_type VARCHAR(20) NOT NULL,
                quantity NUMERIC(10, 2) NOT NULL,
                occurred_at DATETIME NOT NULL,
                reason VARCHAR(255),
                notes TEXT
            );
            CREATE INDEX ix_inventory_events_batch_id ON inventory_events (batch_id);
            CREATE INDEX ix_inventory_events_event_type ON inventory_events (event_type);
            CREATE INDEX ix_inventory_events_occurred_at ON inventory_events (occurred_at);
            """
        )
        connection.execute(
            "INSERT INTO users (id,email,hashed_password,display_name,is_active) VALUES (?,?,?,?,?)",
            (9, "legacy@provision.local", "legacy-hash", "Legacy User", 0),
        )
        connection.execute(
            "INSERT INTO products (id,name,brand,category,source) VALUES (?,?,?,?,?)",
            (41, "Legacy Tuna", "Provision", "Canned Goods", ProductSource.USER_CONFIRMED.value),
        )
        connection.execute(
            "INSERT INTO storage_locations (id,name) VALUES (?,?)", (15, "Legacy Pantry")
        )
        connection.execute(
            "INSERT INTO grocery_sessions "
            "(id,store_name,purchase_date,total_amount,status,idempotency_key,idempotency_fingerprint) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                23,
                "Legacy Market",
                purchased_at.isoformat(),
                "108.50",
                GrocerySessionStatus.COMPLETED.value,
                "legacy-session-key",
                "legacy-fingerprint",
            ),
        )
        connection.execute(
            "INSERT INTO inventory_batches "
            "(id,product_id,storage_location_id,grocery_session_id,purchased_at,expiration_date,"
            "original_quantity,remaining_quantity,unit_price) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                67,
                41,
                15,
                23,
                purchased_at.isoformat(),
                date(2027, 10, 30).isoformat(),
                "4.00",
                "3.00",
                "27.13",
            ),
        )
        connection.execute(
            "INSERT INTO shopping_list_items (id,product_id,name,quantity,unit,is_bought) "
            "VALUES (?,?,?,?,?,?)",
            (81, 41, "Legacy Tuna", "2.00", "can", 1),
        )
        connection.execute(
            "INSERT INTO inventory_events "
            "(id,batch_id,event_type,quantity,occurred_at,reason) VALUES (?,?,?,?,?,?)",
            (
                102,
                67,
                EventType.PURCHASED.value,
                "4.00",
                purchased_at.isoformat(),
                "Legacy import test",
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return path


def _run_alembic(engine, *arguments):
    environment = os.environ.copy()
    environment["DATABASE_URL"] = engine.url.difference_update_query(
        ["options"]
    ).render_as_string(hide_password=False)
    environment["JWT_SECRET_KEY"] = "sqlite-import-migration-test-secret"
    options = engine.url.query.get("options", "")
    schema = options.partition("=")[2]
    if schema:
        environment["PGOPTIONS"] = f"-c search_path={schema}"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=BACKEND_DIR,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"alembic {' '.join(arguments)} failed\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def _target_counts_are_zero(engine):
    assert get_postgres_table_counts(engine) == {name: 0 for name in TABLES_IN_DEPENDENCY_ORDER}


@pytest.fixture
def import_target(postgres_test_schema):
    owned = create_owned_test_schema(postgres_test_schema.database_url)
    engine = create_engine(owned.scoped_url, pool_pre_ping=True)
    try:
        _run_alembic(engine, "upgrade", "a4d9c69b8f21")
        with schema_without_owner_marker(owned, engine):
            yield engine
    finally:
        engine.dispose()
        drop_owned_test_schema(owned)


def test_legacy_transfer_converts_values_verifies_and_syncs_sequences(
    import_target, tmp_path
):
    source_path = create_legacy_database(tmp_path / "legacy.sqlite")

    success, message = migrate_data(source_path, import_target)

    assert success, message
    assert "in-transaction verification completed" in message
    with sqlite3.connect(source_path) as source:
        assert source.execute("SELECT is_active FROM users WHERE id = 9").fetchone()[0] == 0
        assert source.execute(
            "SELECT is_bought FROM shopping_list_items WHERE id = 81"
        ).fetchone()[0] == 1

    assert main(
        [
            "--sqlite-path",
            str(source_path),
            "--postgres-url",
            import_target.url.render_as_string(hide_password=False),
            "--verify-only",
        ]
    ) == 0

    _run_alembic(import_target, "upgrade", "head")

    with Session(import_target) as session:
        user = session.get(User, 9)
        shopping_item = session.get(ShoppingListItem, 81)
        batch = session.get(InventoryBatch, 67)
        grocery_session = session.get(GrocerySession, 23)
        household = session.get(Household, batch.household_id)
        default_membership = session.scalar(
            select(HouseholdMembership).where(
                HouseholdMembership.user_id == user.id,
                HouseholdMembership.is_default.is_(True),
            )
        )
        assert user.is_active is False
        assert shopping_item.is_bought is True
        assert batch.unit_price == Decimal("27.13")
        assert batch.expiration_date == date(2027, 10, 30)
        assert batch.purchased_at == datetime(2026, 10, 30, 8, 45, 12, tzinfo=timezone.utc)
        assert grocery_session.total_amount == Decimal("108.50")
        assert household.slug == "legacy-quarantine"
        assert session.scalar(
            select(func.count(HouseholdMembership.id)).where(
                HouseholdMembership.household_id == household.id
            )
        ) == 0
        assert default_membership is not None
        assert default_membership.role == HouseholdRole.OWNER.value
        assert session.get(Household, default_membership.household_id).slug == f"user-{user.id}"

        next_product = Product(
            household_id=household.id,
            name="After import",
            source=ProductSource.USER_CONFIRMED,
        )
        session.add(next_product)
        session.commit()
        assert next_product.id > 41


def test_import_refuses_nonempty_target_without_changing_existing_rows(import_target, tmp_path):
    source_path = create_legacy_database(tmp_path / "legacy.sqlite")
    with import_target.begin() as connection:
        existing_id = connection.execute(
            text(
                "INSERT INTO products (name, source) "
                "VALUES ('Keep existing target data', 'USER_CONFIRMED') RETURNING id"
            )
        ).scalar_one()

    success, message = migrate_data(source_path, import_target)

    assert not success
    assert "target is not empty" in message
    with import_target.connect() as connection:
        products = connection.execute(text("SELECT id, name FROM products")).all()
        assert products == [(existing_id, "Keep existing target data")]
        assert connection.execute(text("SELECT count(*) FROM users")).scalar_one() == 0


def test_verification_mismatch_rolls_back_all_imported_rows(import_target, tmp_path):
    source_path = create_legacy_database(tmp_path / "legacy.sqlite")
    with import_target.begin() as connection:
        connection.execute(
            text(
                "CREATE FUNCTION corrupt_imported_product() RETURNS trigger "
                "LANGUAGE plpgsql AS $$ BEGIN NEW.name := upper(NEW.name); "
                "RETURN NEW; END $$"
            )
        )
        connection.execute(
            text(
                "CREATE TRIGGER corrupt_imported_product_before_insert "
                "BEFORE INSERT ON products FOR EACH ROW "
                "EXECUTE FUNCTION corrupt_imported_product()"
            )
        )

    try:
        success, message = migrate_data(source_path, import_target)
        assert not success
        assert "Value mismatch in 'products'" in message
        _target_counts_are_zero(import_target)
    finally:
        with import_target.begin() as connection:
            connection.execute(
                text("DROP TRIGGER IF EXISTS corrupt_imported_product_before_insert ON products")
            )
            connection.execute(text("DROP FUNCTION IF EXISTS corrupt_imported_product()"))

    with import_target.begin() as connection:
        next_product_id = connection.execute(
            text(
                "INSERT INTO products (name, source) "
                "VALUES ('Sequence after rollback', 'USER_CONFIRMED') RETURNING id"
            )
        ).scalar_one()
        assert next_product_id == 1


def test_verify_only_exits_nonzero_when_postgres_values_do_not_match(import_target, tmp_path):
    source_path = create_legacy_database(tmp_path / "legacy.sqlite")

    exit_code = main(
        [
            "--sqlite-path",
            str(source_path),
            "--postgres-url",
            import_target.url.render_as_string(hide_password=False),
            "--verify-only",
        ]
    )

    assert exit_code == 1
    _target_counts_are_zero(import_target)


def test_current_household_head_is_rejected_as_legacy_import_target(
    import_target, tmp_path
):
    source_path = create_legacy_database(tmp_path / "legacy.sqlite")
    _run_alembic(import_target, "upgrade", "head")

    success, message = migrate_data(source_path, import_target)

    assert not success
    assert "revision a4d9c69b8f21" in message
    with import_target.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM households")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM products")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM users")).scalar_one() == 0


def test_sqlite_backup_includes_committed_wal_pages_without_source_writes(tmp_path):
    source_path = tmp_path / "legacy-wal.sqlite"
    writer = sqlite3.connect(source_path)
    try:
        assert writer.execute("PRAGMA journal_mode = WAL").fetchone()[0].lower() == "wal"
        writer.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        writer.commit()
        writer.execute("INSERT INTO records (id, value) VALUES (1, 'committed in WAL')")
        writer.commit()

        wal_path = Path(f"{source_path}-wal")
        assert wal_path.is_file()
        before = {
            path: path.read_bytes()
            for path in (source_path, wal_path)
        }

        backup_path = create_sqlite_backup(source_path, tmp_path / "backups")

        after = {path: path.read_bytes() for path in before}
        assert after == before
        with sqlite3.connect(backup_path) as backup:
            assert backup.execute("SELECT value FROM records WHERE id = 1").fetchone() == (
                "committed in WAL",
            )
        assert writer.execute("SELECT value FROM records WHERE id = 1").fetchone() == (
            "committed in WAL",
        )
    finally:
        writer.close()
