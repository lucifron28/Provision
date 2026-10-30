import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from app.models import Base
from app.models.batch import InventoryBatch
from app.models.event import EventType, InventoryEvent
from app.models.location import StorageLocation
from app.models.product import Product, ProductSource
from app.models.session import GrocerySession, GrocerySessionStatus
from app.models.shopping import ShoppingListItem
from app.models.user import User
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


def _sqlite_url(path):
    return URL.create("sqlite", database=str(path))


def create_legacy_database(path):
    sqlite_engine = create_engine(_sqlite_url(path))
    Base.metadata.create_all(sqlite_engine)
    purchased_at = datetime(2026, 10, 30, 8, 45, 12, tzinfo=timezone.utc)
    with Session(sqlite_engine) as session:
        session.add_all(
            [
                User(
                    id=9,
                    email="legacy@provision.local",
                    hashed_password="legacy-hash",
                    display_name="Legacy User",
                    is_active=False,
                ),
                Product(
                    id=41,
                    name="Legacy Tuna",
                    brand="Provision",
                    category="Canned Goods",
                    source=ProductSource.USER_CONFIRMED,
                ),
                StorageLocation(id=15, name="Legacy Pantry"),
                GrocerySession(
                    id=23,
                    store_name="Legacy Market",
                    purchase_date=purchased_at,
                    total_amount=Decimal("108.50"),
                    status=GrocerySessionStatus.COMPLETED,
                    idempotency_key="legacy-session-key",
                    idempotency_fingerprint="legacy-fingerprint",
                ),
                InventoryBatch(
                    id=67,
                    product_id=41,
                    storage_location_id=15,
                    grocery_session_id=23,
                    purchased_at=purchased_at,
                    expiration_date=date(2027, 10, 30),
                    original_quantity=Decimal("4.00"),
                    remaining_quantity=Decimal("3.00"),
                    unit_price=Decimal("27.13"),
                ),
                ShoppingListItem(
                    id=81,
                    product_id=41,
                    name="Legacy Tuna",
                    quantity=Decimal("2.00"),
                    unit="can",
                    is_bought=True,
                ),
                InventoryEvent(
                    id=102,
                    batch_id=67,
                    event_type=EventType.PURCHASED,
                    quantity=Decimal("4.00"),
                    occurred_at=purchased_at,
                    reason="Legacy import test",
                ),
            ]
        )
        session.commit()
    sqlite_engine.dispose()
    return path


def _target_counts_are_zero(engine):
    assert get_postgres_table_counts(engine) == {name: 0 for name in TABLES_IN_DEPENDENCY_ORDER}


@pytest.fixture
def import_target(postgres_test_schema):
    owned = create_owned_test_schema(postgres_test_schema.database_url)
    engine = create_engine(owned.scoped_url, pool_pre_ping=True)
    try:
        Base.metadata.create_all(engine)
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

    with Session(import_target) as session:
        user = session.get(User, 9)
        shopping_item = session.get(ShoppingListItem, 81)
        batch = session.get(InventoryBatch, 67)
        grocery_session = session.get(GrocerySession, 23)
        assert user.is_active is False
        assert shopping_item.is_bought is True
        assert batch.unit_price == Decimal("27.13")
        assert batch.expiration_date == date(2027, 10, 30)
        assert batch.purchased_at == datetime(2026, 10, 30, 8, 45, 12, tzinfo=timezone.utc)
        assert grocery_session.total_amount == Decimal("108.50")

    assert main(
        [
            "--sqlite-path",
            str(source_path),
            "--postgres-url",
            import_target.url.render_as_string(hide_password=False),
            "--verify-only",
        ]
    ) == 0

    with Session(import_target) as session:
        next_product = Product(
            name="After import",
            source=ProductSource.USER_CONFIRMED,
        )
        session.add(next_product)
        session.commit()
        assert next_product.id > 41


def test_import_refuses_nonempty_target_without_changing_existing_rows(import_target, tmp_path):
    source_path = create_legacy_database(tmp_path / "legacy.sqlite")
    with Session(import_target) as session:
        session.add(Product(name="Keep existing target data"))
        session.commit()
        existing_id = session.scalar(
            select(Product.id).where(Product.name == "Keep existing target data")
        )

    success, message = migrate_data(source_path, import_target)

    assert not success
    assert "target is not empty" in message
    with Session(import_target) as session:
        products = session.scalars(select(Product)).all()
        assert [(product.id, product.name) for product in products] == [
            (existing_id, "Keep existing target data")
        ]
        assert session.scalar(select(func.count()).select_from(User)) == 0


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

    with Session(import_target) as session:
        next_product = Product(name="Sequence after rollback")
        session.add(next_product)
        session.commit()
        assert next_product.id == 1


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
