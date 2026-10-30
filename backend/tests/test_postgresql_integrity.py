"""
PostgreSQL Specific Regression and Integrity Test Suite.

Validates behavior specific to PostgreSQL:
- Strict foreign key RESTRICT constraints
- Transaction rollback and isolation
- Unique constraint violations and PostgreSQL sequence management
- Native PostgreSQL ENUM validation
- Numeric precision preservation
- Idempotent session concurrency handling
"""

import threading
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.models.product import Product, ProductSource
from app.models.location import StorageLocation
from app.models.batch import InventoryBatch
from app.models.event import InventoryEvent, EventType
from app.models.session import GrocerySession, GrocerySessionStatus
from app.models.user import User


def test_postgresql_dialect_active(engine):
    """Verifies tests run against PostgreSQL 18, never a SQLite fallback."""
    assert engine.dialect.name == "postgresql"
    with engine.connect() as conn:
        version_num = conn.execute(text("SHOW server_version_num")).scalar_one()
        assert int(version_num) // 10000 == 18
        version_str = conn.execute(text("SELECT version();")).scalar_one()
        assert "PostgreSQL 18" in version_str


def test_postgresql_foreign_key_restrict_product_deletion(db, engine, auth_household):
    """PostgreSQL strictly enforces ON DELETE RESTRICT on product_id in inventory_batches."""
    prod = Product(
        household_id=auth_household.id,
        name="Century Tuna Flakes",
        brand="Century",
        category="Canned Goods",
        source=ProductSource.USER_CONFIRMED,
    )
    db.add(prod)
    db.commit()
    db.refresh(prod)

    batch = InventoryBatch(
        household_id=auth_household.id,
        product_id=prod.id,
        purchased_at=datetime.now(timezone.utc),
        original_quantity=10.0,
        remaining_quantity=10.0,
    )
    db.add(batch)
    db.commit()

    # Attempting to delete product while referenced by batch must fail with IntegrityError
    db.delete(prod)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_postgresql_foreign_key_restrict_batch_deletion(db, auth_household):
    """PostgreSQL strictly enforces ON DELETE RESTRICT on batch_id in inventory_events."""
    prod = Product(
        household_id=auth_household.id,
        name="Eden Cheese",
        brand="Eden",
        source=ProductSource.USER_CONFIRMED,
    )
    db.add(prod)
    db.commit()

    batch = InventoryBatch(
        household_id=auth_household.id,
        product_id=prod.id,
        purchased_at=datetime.now(timezone.utc),
        original_quantity=5.0,
        remaining_quantity=5.0,
    )
    db.add(batch)
    db.commit()

    event = InventoryEvent(
        batch_id=batch.id,
        event_type=EventType.PURCHASED,
        quantity=5.0,
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(event)
    db.commit()

    # Attempting to delete batch while referenced by event must fail
    db.delete(batch)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_postgresql_idempotency_key_unique_within_household(db, auth_household):
    """The idempotency key is unique within a household and reusable elsewhere."""
    from app.models.household import Household

    other_household = Household(name="Other", slug="other-idempotency-household")
    db.add(other_household)
    db.flush()
    session1 = GrocerySession(
        household_id=auth_household.id,
        store_name="Robinsons Supermarket",
        purchase_date=datetime.now(timezone.utc),
        status=GrocerySessionStatus.COMPLETED,
        idempotency_key="idemp-key-unique-test",
    )
    db.add(session1)
    db.commit()

    session2 = GrocerySession(
        household_id=other_household.id,
        store_name="Puregold",
        purchase_date=datetime.now(timezone.utc),
        status=GrocerySessionStatus.COMPLETED,
        idempotency_key="idemp-key-unique-test",
    )
    db.add(session2)
    db.commit()

    same_household_duplicate = GrocerySession(
        household_id=auth_household.id,
        store_name="Another Store",
        purchase_date=datetime.now(timezone.utc),
        status=GrocerySessionStatus.COMPLETED,
        idempotency_key="idemp-key-unique-test",
    )
    db.add(same_household_duplicate)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_postgresql_numeric_precision_preservation(db, auth_household):
    """PostgreSQL Numeric(10, 2) columns maintain exact currency and quantity decimals."""
    prod = Product(
        household_id=auth_household.id,
        name="Datu Puti Vinegar",
        source=ProductSource.USER_CONFIRMED,
    )
    db.add(prod)
    db.commit()

    test_price = Decimal("42.50")
    test_qty = 12.75

    batch = InventoryBatch(
        household_id=auth_household.id,
        product_id=prod.id,
        purchased_at=datetime.now(timezone.utc),
        original_quantity=test_qty,
        remaining_quantity=test_qty,
        unit_price=test_price,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    assert float(batch.remaining_quantity) == 12.75
    assert batch.unit_price == Decimal("42.50")


def test_postgresql_transaction_isolation_uncommitted_reads(engine):
    """PostgreSQL Read Committed isolation prevents dirty reads across concurrent connections."""
    from sqlalchemy.orm import sessionmaker

    SessionLocal = sessionmaker(bind=engine)
    session_a = SessionLocal()
    session_b = SessionLocal()

    try:
        user = User(
            email="isolated_read@provision.local",
            hashed_password="hash",
            is_active=True,
        )
        session_a.add(user)
        session_a.flush()  # Flushed to buffer but uncommitted

        # Session B should NOT see user yet
        user_in_b = session_b.query(User).filter_by(email="isolated_read@provision.local").first()
        assert user_in_b is None

        session_a.commit()

        # After commit, Session B sees the committed user
        user_in_b_after = session_b.query(User).filter_by(email="isolated_read@provision.local").first()
        assert user_in_b_after is not None
        assert user_in_b_after.email == "isolated_read@provision.local"
    finally:
        session_a.close()
        session_b.close()


def test_postgresql_concurrent_write_idempotency_collision(engine, auth_household):
    """Concurrent writes with the same idempotency key are safely handled via unique constraints."""
    from sqlalchemy.orm import sessionmaker

    SessionLocal = sessionmaker(bind=engine)
    results = []

    def attempt_insert(store_name: str, key: str, household_id: int):
        session = SessionLocal()
        try:
            gs = GrocerySession(
                household_id=household_id,
                store_name=store_name,
                purchase_date=datetime.now(timezone.utc),
                status=GrocerySessionStatus.DRAFT,
                idempotency_key=key,
            )
            session.add(gs)
            session.commit()
            results.append("SUCCESS")
        except IntegrityError:
            session.rollback()
            results.append("COLLISION")
        finally:
            session.close()

    shared_key = "concurrent-idemp-test-key"
    t1 = threading.Thread(
        target=attempt_insert, args=("Store A", shared_key, auth_household.id)
    )
    t2 = threading.Thread(
        target=attempt_insert, args=("Store B", shared_key, auth_household.id)
    )

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Exactly one must succeed and one must be caught by PostgreSQL unique constraint
    assert sorted(results) == ["COLLISION", "SUCCESS"]
