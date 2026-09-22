"""
Comprehensive tests for Provision Philippine grocery database seeding,
analytics endpoints, FEFO multi-batch consumption, and data integrity.
"""

import os
import sqlite3
from datetime import date, timedelta
from decimal import Decimal
import pytest

from app.core.security import verify_password
from app.models.product import Product
from app.models.location import StorageLocation
from app.models.session import GrocerySession, GrocerySessionStatus
from app.models.batch import InventoryBatch
from app.models.event import InventoryEvent, EventType
from app.models.shopping import ShoppingListItem
from app.models.user import User
from seed import seed_database


@pytest.fixture
def seeded_db(db):
    """Seed the in-memory test database and return the session."""
    seed_database(reset=True, db=db)
    return db


@pytest.fixture
def seeded_client(client, seeded_db):
    """Client backed by the fully seeded database."""
    return client


def test_seed_database_execution(seeded_db):
    """
    Verify that seed_database populates products, locations, sessions,
    batches, events, shopping items, and demo users without errors.
    """
    user_count = seeded_db.query(User).count()
    loc_count = seeded_db.query(StorageLocation).count()
    sess_count = seeded_db.query(GrocerySession).count()
    prod_count = seeded_db.query(Product).count()
    batch_count = seeded_db.query(InventoryBatch).count()
    active_batches = (
        seeded_db.query(InventoryBatch)
        .filter(InventoryBatch.remaining_quantity > 0)
        .count()
    )
    event_count = seeded_db.query(InventoryEvent).count()
    shop_count = seeded_db.query(ShoppingListItem).count()

    assert user_count >= 2, f"Expected at least 2 users, found {user_count}"
    assert loc_count == 7, f"Expected 7 storage locations, found {loc_count}"
    assert sess_count == 4, f"Expected 4 grocery sessions, found {sess_count}"
    assert prod_count == 49, f"Expected 49 products, found {prod_count}"
    assert batch_count == 37, f"Expected 37 batches, found {batch_count}"
    assert active_batches == 34, f"Expected 34 active batches, found {active_batches}"
    assert event_count == 62, f"Expected 62 inventory events, found {event_count}"
    assert shop_count == 9, f"Expected 9 shopping items, found {shop_count}"

    # Verify demo credentials
    demo_user = seeded_db.query(User).filter(User.email == "user@provision.local").first()
    assert demo_user is not None
    assert demo_user.display_name == "Maria Santos"
    assert verify_password("password123", demo_user.hashed_password)

    demo_alt = seeded_db.query(User).filter(User.email == "demo@provision.local").first()
    assert demo_alt is not None
    assert demo_alt.display_name == "Juan Dela Cruz"
    assert verify_password("password123", demo_alt.hashed_password)

    # Verify key Philippine products exist with valid 480 barcodes
    century_tuna = (
        seeded_db.query(Product)
        .filter(Product.name == "Century Tuna Flakes in Oil")
        .first()
    )
    assert century_tuna is not None
    assert century_tuna.barcode == "4800016644818"
    assert century_tuna.brand == "Century Tuna"
    assert century_tuna.category == "Canned Goods"

    pancit_canton = (
        seeded_db.query(Product)
        .filter(Product.name == "Lucky Me! Pancit Canton Kalamansi")
        .first()
    )
    assert pancit_canton is not None
    assert pancit_canton.barcode.startswith("480")

    # Verify relationship and foreign key integrity
    for batch in seeded_db.query(InventoryBatch).all():
        assert batch.product is not None, f"Batch {batch.id} missing product"
        assert batch.storage_location is not None, f"Batch {batch.id} missing location"
        assert batch.grocery_session is not None, f"Batch {batch.id} missing session"

    for event in seeded_db.query(InventoryEvent).all():
        assert event.batch is not None, f"Event {event.id} missing batch"
        assert event.quantity != 0, f"Event {event.id} has zero quantity"
        if event.event_type in [EventType.PURCHASED, EventType.CONSUMED, EventType.DISCARDED, EventType.EXPIRED]:
            assert event.quantity > 0, f"Event {event.id} ({event.event_type}) has non-positive quantity"

def test_analytics_inventory_summary(seeded_client):
    """
    Verify /api/v1/analytics/inventory-summary returns on-hand products
    with locations and stock counts matching Philippine demo catalog.
    """
    res = seeded_client.get("/api/v1/analytics/inventory-summary")
    assert res.status_code == 200
    data = res.json()

    assert len(data) == 32  # 32 products with active on-hand inventory
    prod_map = {item["product_name"]: item for item in data}

    # Century Tuna Flakes in Oil has 2 active batches totaling 16.0 cans
    assert "Century Tuna Flakes in Oil" in prod_map
    tuna = prod_map["Century Tuna Flakes in Oil"]
    assert tuna["total_remaining"] == 16.0
    assert tuna["active_batches_count"] == 2
    assert "Pantry - Shelf A" in tuna["locations"]

    # Harvester's Dinorado Special Rice
    assert "Harvester's Dinorado Special Rice" in prod_map
    rice = prod_map["Harvester's Dinorado Special Rice"]
    assert rice["total_remaining"] == 4.0
    assert "Pantry - Shelf B" in rice["locations"]

    # Purefoods Tender Juicy Hotdog in Freezer
    assert "Purefoods Tender Juicy Hotdog Classic" in prod_map
    hotdog = prod_map["Purefoods Tender Juicy Hotdog Classic"]
    assert hotdog["total_remaining"] == 1.0
    assert "Freezer" in hotdog["locations"]


def test_analytics_expiring_soon(seeded_client):
    """
    Verify /api/v1/analytics/expiring-soon correctly detects urgent
    expiration items (Magnolia Fresh Milk, Gardenia Bread, Bounty Fresh Eggs).
    """
    res = seeded_client.get("/api/v1/analytics/expiring-soon?days=7")
    assert res.status_code == 200
    items = res.json()

    # 3 batches expire within 7 days
    assert len(items) == 3
    exp_names = [item["product_name"] for item in items]
    assert "Magnolia Fresh Milk" in exp_names
    assert "Gardenia Classic White Bread" in exp_names
    assert "Bounty Fresh Farm Eggs (Medium Dozen)" in exp_names

    # Items should be ordered ascending by expiration date
    days_left = [item["days_until_expiration"] for item in items]
    assert days_left == sorted(days_left)
    assert days_left[0] == 1  # Magnolia Milk in 1 day
    assert days_left[1] == 2  # Gardenia Bread in 2 days
    assert days_left[2] == 4  # Eggs in 4 days

    # Narrowing horizon to 1 day should yield only Magnolia Fresh Milk
    res_1day = seeded_client.get("/api/v1/analytics/expiring-soon?days=1")
    assert res_1day.status_code == 200
    items_1day = res_1day.json()
    assert len(items_1day) == 1
    assert items_1day[0]["product_name"] == "Magnolia Fresh Milk"


def test_analytics_low_stock(seeded_client):
    """
    Verify /api/v1/analytics/low-stock flags products with stock <= threshold,
    including partially consumed staples and out-of-stock items.
    """
    res = seeded_client.get("/api/v1/analytics/low-stock?threshold=1.0")
    assert res.status_code == 200
    items = res.json()

    low_names = {item["product_name"]: item["current_stock"] for item in items}

    # Lucky Me! Pancit Canton Kalamansi has 1 pack remaining
    assert "Lucky Me! Pancit Canton Kalamansi" in low_names
    assert low_names["Lucky Me! Pancit Canton Kalamansi"] == 1.0

    # Datu Puti Soy Sauce has 0.3 L remaining
    assert "Datu Puti Soy Sauce" in low_names
    assert low_names["Datu Puti Soy Sauce"] == 0.3

    # Argentina Corned Beef is completely out of stock (0.0 remaining)
    assert "Argentina Corned Beef" in low_names
    assert low_names["Argentina Corned Beef"] == 0.0

    # Knorr Sinigang sa Sampalok has 1.0 pack remaining
    assert "Knorr Sinigang sa Sampalok Mix Original" in low_names
    assert low_names["Knorr Sinigang sa Sampalok Mix Original"] == 1.0


def test_analytics_valuation(seeded_client):
    """
    Verify /api/v1/analytics/valuation calculates total pantry value
    and active product/batch counts in PHP.
    """
    res = seeded_client.get("/api/v1/analytics/valuation")
    assert res.status_code == 200
    data = res.json()

    assert data["total_active_batches"] == 34
    assert data["total_active_products"] == 32
    assert Decimal(str(data["total_value"])) == Decimal("4852.56")


def test_analytics_spending(seeded_client):
    """
    Verify /api/v1/analytics/spending totals only completed sessions
    (SM Supermarket, Savemore, Puregold) and excludes draft sessions.
    """
    res = seeded_client.get("/api/v1/analytics/spending")
    assert res.status_code == 200
    data = res.json()

    assert data["sessions_count"] == 3
    # 3450.75 (SM) + 1820.50 (Savemore) + 2685.00 (Puregold) = 7956.25
    assert Decimal(str(data["total_spent"])) == Decimal("7956.25")

    stores = [tx["store_name"] for tx in data["recent_transactions"]]
    assert any("SM Supermarket" in s for s in stores)
    assert any("Savemore" in s for s in stores)
    assert any("Puregold" in s for s in stores)
    assert not any("Robinsons" in s for s in stores)  # Robinsons is DRAFT


def test_analytics_waste(seeded_client):
    """
    Verify /api/v1/analytics/waste calculates monetary loss and quantities
    from expired and discarded items (Gardenia Bread and Calamansi).
    """
    res = seeded_client.get("/api/v1/analytics/waste")
    assert res.status_code == 200
    data = res.json()

    assert data["total_waste_events"] == 2
    assert data["total_quantity_wasted"] == 201.0  # 1 loaf + 200g
    # ₱82.00 (Gardenia bread) + ₱18.00 (Calamansi) = ₱100.00
    assert Decimal(str(data["total_financial_loss"])) == Decimal("100.00")

    wasted_names = [item["product_name"] for item in data["wasted_items"]]
    assert "Gardenia Classic White Bread" in wasted_names
    assert "Fresh Native Calamansi" in wasted_names


def test_analytics_price_history(seeded_client, seeded_db):
    """
    Verify /api/v1/analytics/price-history/{id} shows historical prices
    and stores for multi-intake products (Century Tuna & Purefoods Corned Beef).
    """
    # 1. Century Tuna Flakes in Oil (SM Megamall ₱43.50, Puregold ₱45.00)
    tuna = (
        seeded_db.query(Product)
        .filter(Product.name == "Century Tuna Flakes in Oil")
        .first()
    )
    res_tuna = seeded_client.get(f"/api/v1/analytics/price-history/{tuna.id}")
    assert res_tuna.status_code == 200
    data_tuna = res_tuna.json()

    assert data_tuna["product_id"] == tuna.id
    assert len(data_tuna["price_points"]) == 2
    prices_tuna = [Decimal(str(pt["unit_price"])) for pt in data_tuna["price_points"]]
    assert Decimal("43.50") in prices_tuna
    assert Decimal("45.00") in prices_tuna

    # 2. Purefoods Corned Beef Classic (SM ₱98.50, Puregold ₱102.00)
    beef = (
        seeded_db.query(Product)
        .filter(Product.name == "Purefoods Corned Beef Classic")
        .first()
    )
    res_beef = seeded_client.get(f"/api/v1/analytics/price-history/{beef.id}")
    assert res_beef.status_code == 200
    data_beef = res_beef.json()

    assert len(data_beef["price_points"]) == 2
    prices_beef = [Decimal(str(pt["unit_price"])) for pt in data_beef["price_points"]]
    assert Decimal("98.50") in prices_beef
    assert Decimal("102.00") in prices_beef


def test_fefo_consumption_on_century_tuna(seeded_client, seeded_db):
    """
    Verify First-Expired-First-Out (FEFO) logic on Century Tuna:
    Batch 1: 4 cans expiring in 90 days (earlier)
    Batch 2: 12 cans expiring in 365 days (later)
    Consuming 6 cans should exhaust Batch 1 (4 cans) and take 2 cans from Batch 2.
    """
    tuna = (
        seeded_db.query(Product)
        .filter(Product.name == "Century Tuna Flakes in Oil")
        .first()
    )
    batches = (
        seeded_db.query(InventoryBatch)
        .filter(
            InventoryBatch.product_id == tuna.id,
            InventoryBatch.remaining_quantity > 0,
        )
        .order_by(InventoryBatch.expiration_date.asc())
        .all()
    )
    assert len(batches) == 2
    early_batch = batches[0]
    later_batch = batches[1]
    assert early_batch.remaining_quantity == 4.0
    assert later_batch.remaining_quantity == 12.0

    # Consume 6 cans
    payload = {
        "product_id": tuna.id,
        "quantity": 6.0,
        "reason": "Family tuna pasta merienda",
    }
    res = seeded_client.post("/api/v1/inventory/consume", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["total_consumed"] == 6.0
    assert data["new_total_stock"] == 10.0  # 16 - 6 = 10

    # Verify deductions order: early batch first, then later batch
    deductions = data["batches_deducted"]
    assert len(deductions) == 2

    # Deduction 1: Earliest expiring batch (all 4 cans exhausted)
    assert deductions[0]["batch_id"] == early_batch.id
    assert deductions[0]["quantity_deducted"] == 4.0
    assert deductions[0]["remaining_in_batch"] == 0.0

    # Deduction 2: Later batch (2 cans deducted, 10 remaining)
    assert deductions[1]["batch_id"] == later_batch.id
    assert deductions[1]["quantity_deducted"] == 2.0
    assert deductions[1]["remaining_in_batch"] == 10.0

    # Verify audit events were recorded
    events_res = seeded_client.get("/api/v1/inventory/events?event_type=CONSUMED")
    assert events_res.status_code == 200
    events = events_res.json()
    tuna_events = [
        ev for ev in events if ev.get("reason") == "Family tuna pasta merienda"
    ]
    assert len(tuna_events) == 2
    assert sum(ev["quantity"] for ev in tuna_events) == 6.0


def test_provision_db_file_on_disk():
    """
    Verify backend/provision.db file on disk contains seeded data,
    passes foreign key checks, and has active demo credentials.
    """
    db_path = os.path.join(os.path.dirname(__file__), "..", "provision.db")
    if not os.path.exists(db_path):
        pytest.skip(f"provision.db not found on disk at {db_path} (run python seed.py to create)")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check SQLite foreign keys
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute("PRAGMA foreign_key_check;")
        fk_errors = cursor.fetchall()
        assert fk_errors == [], f"Foreign key check failed: {fk_errors}"

        # Verify row counts
        counts = {}
        for table in [
            "users",
            "storage_locations",
            "grocery_sessions",
            "products",
            "inventory_batches",
            "inventory_events",
            "shopping_list_items",
        ]:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = cursor.fetchone()[0]

        assert counts["users"] >= 2
        assert counts["storage_locations"] == 7
        assert counts["grocery_sessions"] == 4
        assert counts["products"] == 49
        assert counts["inventory_batches"] == 37
        assert counts["inventory_events"] == 62
        assert counts["shopping_list_items"] == 9

        # Verify demo user credentials exist in on-disk SQLite
        cursor.execute(
            "SELECT hashed_password FROM users WHERE email = 'user@provision.local'"
        )
        row = cursor.fetchone()
        assert row is not None, "user@provision.local missing from provision.db"
        assert verify_password("password123", row[0])

    finally:
        conn.close()


def test_seed_idempotency_and_user_preservation(db):
    """
    Verify that seed_database preserves existing custom users and is idempotent
    when executed repeatedly with reset=True.
    """
    # Create custom user
    custom_user = User(
        email="custom_resident@provision.local",
        hashed_password="dummy_hashed_password",
        display_name="Custom Resident",
        is_active=True,
    )
    db.add(custom_user)
    db.commit()

    # First seed run
    seed_database(reset=True, db=db)
    u1 = db.query(User).filter(User.email == "custom_resident@provision.local").first()
    assert u1 is not None
    assert u1.display_name == "Custom Resident"

    prod_count_1 = db.query(Product).count()
    batch_count_1 = db.query(InventoryBatch).count()
    event_count_1 = db.query(InventoryEvent).count()

    # Second seed run (idempotency check)
    seed_database(reset=True, db=db)
    u2 = db.query(User).filter(User.email == "custom_resident@provision.local").first()
    assert u2 is not None
    assert u2.display_name == "Custom Resident"

    assert db.query(Product).count() == prod_count_1 == 49
    assert db.query(InventoryBatch).count() == batch_count_1 == 37
    assert db.query(InventoryEvent).count() == event_count_1 == 62


def test_seed_non_reset_mode(db):
    """
    Verify that seed_database(reset=False) succeeds without crashing on
    unique constraints and does not duplicate records.
    """
    # Initial seed
    seed_database(reset=True, db=db)

    loc_count = db.query(StorageLocation).count()
    prod_count = db.query(Product).count()
    batch_count = db.query(InventoryBatch).count()
    shop_count = db.query(ShoppingListItem).count()

    # Run again with reset=False
    seed_database(reset=False, db=db)

    assert db.query(StorageLocation).count() == loc_count == 7
    assert db.query(Product).count() == prod_count == 49
    assert db.query(InventoryBatch).count() == batch_count == 37
    assert db.query(ShoppingListItem).count() == shop_count == 9
