"""
Tests for Philippine household calendar date handling (Asia/Manila)
and UTC timestamp preservation.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo
import pytest

from app.core.time import PH_TIMEZONE, household_today
from app.models.product import Product, ProductSource
from app.models.location import StorageLocation
from app.models.batch import InventoryBatch
from app.models.event import InventoryEvent, EventType
from app.schemas.event import DiscardRequest
from app.services.inventory import InventoryService
from seed import seed_database


def test_household_today_manila_timezone():
    """
    Verify that household_today() correctly translates the current time to Asia/Manila.
    At 16:01 UTC, Manila is 00:01 on the NEXT calendar day.
    At 15:59 UTC, Manila is 23:59 on the CURRENT calendar day.
    """
    assert PH_TIMEZONE == ZoneInfo("Asia/Manila")

    # Fixed UTC moment: 2026-09-22 15:59:00 UTC -> 2026-09-22 23:59:00 PHT
    utc_pre_midnight = datetime(2026, 9, 22, 15, 59, 0, tzinfo=timezone.utc)
    with patch("app.core.time.datetime") as mock_dt:
        mock_dt.now.side_effect = lambda tz=None: utc_pre_midnight.astimezone(tz) if tz else utc_pre_midnight
        assert household_today() == date(2026, 9, 22)

    # Fixed UTC moment: 2026-09-22 16:01:00 UTC -> 2026-09-23 00:01:00 PHT (next day in Manila!)
    utc_post_midnight = datetime(2026, 9, 22, 16, 1, 0, tzinfo=timezone.utc)
    with patch("app.core.time.datetime") as mock_dt:
        mock_dt.now.side_effect = lambda tz=None: utc_post_midnight.astimezone(tz) if tz else utc_post_midnight
        # In UTC calendar date it is 2026-09-22, but in Manila calendar date it is 2026-09-23:
        assert utc_post_midnight.date() == date(2026, 9, 22)
        assert household_today() == date(2026, 9, 23)


def test_discard_batch_expired_classification_at_utc_pht_boundary(db):
    """
    Verify that discard_batch classifies an item as EXPIRED using the Philippine
    household calendar date, rather than UTC date.
    """
    # Create product and location
    product = Product(name="Gardenia Bread", unit="packs", source=ProductSource.USER_CONFIRMED)
    location = StorageLocation(name="Pantry Shelf")
    db.add_all([product, location])
    db.commit()

    # Batch expires on 2026-09-22
    batch = InventoryBatch(
        product_id=product.id,
        storage_location_id=location.id,
        original_quantity=2.0,
        remaining_quantity=2.0,
        expiration_date=date(2026, 9, 22),
        purchased_at=datetime(2026, 9, 15, 8, 0, 0, tzinfo=timezone.utc),
    )
    db.add(batch)
    db.commit()

    # When the discard occurs at 2026-09-22 16:30:00 UTC (2026-09-23 00:30:00 PHT):
    # In UTC, 2026-09-22 is "today" (not yet < today).
    # In PHT, household_today() is 2026-09-23, so 2026-09-22 < 2026-09-23 is True -> EXPIRED.
    frozen_utc = datetime(2026, 9, 22, 16, 30, 0, tzinfo=timezone.utc)
    with patch("app.core.time.datetime") as mock_time_dt, \
         patch("app.services.inventory.datetime") as mock_inv_dt:
        mock_time_dt.now.side_effect = lambda tz=None: frozen_utc.astimezone(tz) if tz else frozen_utc
        mock_inv_dt.now.side_effect = lambda tz=None: frozen_utc if tz == timezone.utc else frozen_utc

        discard_req = DiscardRequest(reason="Moldy bread found in morning check")
        updated_batch = InventoryService.discard_batch(db, batch.id, discard_req)

    assert updated_batch.remaining_quantity == 0.0

    # Verify that the event was classified as EXPIRED (not DISCARDED)
    event = db.query(InventoryEvent).filter(InventoryEvent.batch_id == batch.id).first()
    assert event is not None
    assert event.event_type == EventType.EXPIRED
    # Verify occurred_at remained in UTC
    assert event.occurred_at.hour == 16
    assert event.occurred_at.minute == 30


def test_analytics_expiring_soon_uses_philippine_calendar_date(client, db):
    """
    Verify /analytics/expiring-soon calculates days_left and thresholds using
    household_today() (Asia/Manila), avoiding UTC calendar-day mismatch.
    """
    product = Product(name="Magnolia Fresh Milk", unit="L", source=ProductSource.USER_CONFIRMED)
    location = StorageLocation(name="Fridge Top Shelf")
    db.add_all([product, location])
    db.commit()

    # Batch expires on 2026-09-25
    batch = InventoryBatch(
        product_id=product.id,
        storage_location_id=location.id,
        original_quantity=1.0,
        remaining_quantity=1.0,
        expiration_date=date(2026, 9, 25),
        purchased_at=datetime(2026, 9, 18, 2, 0, 0, tzinfo=timezone.utc),
    )
    db.add(batch)
    db.commit()

    # Time is 2026-09-22 17:00:00 UTC -> 2026-09-23 01:00:00 PHT
    frozen_utc = datetime(2026, 9, 22, 17, 0, 0, tzinfo=timezone.utc)
    with patch("app.core.time.datetime") as mock_time_dt:
        mock_time_dt.now.side_effect = lambda tz=None: frozen_utc.astimezone(tz) if tz else frozen_utc

        res = client.get("/api/v1/analytics/expiring-soon?days=7")
        assert res.status_code == 200
        items = res.json()

        milk_item = next((item for item in items if item["product_name"] == "Magnolia Fresh Milk"), None)
        assert milk_item is not None
        # In PHT it is 2026-09-23. Expiration is 2026-09-25.
        # Days left must be 25 - 23 = 2 days, NOT 25 - 22 = 3 days.
        assert milk_item["days_until_expiration"] == 2


def test_seed_uses_philippine_household_date(db):
    """
    Verify seed_database calculates expiration horizons relative to household_today().
    """
    # Freeze time where UTC and PHT calendar days differ
    # 2026-09-22 17:00:00 UTC -> 2026-09-23 PHT
    frozen_utc = datetime(2026, 9, 22, 17, 0, 0, tzinfo=timezone.utc)
    with patch("app.core.time.datetime") as mock_time_dt:
        mock_time_dt.now.side_effect = lambda tz=None: frozen_utc.astimezone(tz) if tz else frozen_utc

        seed_database(reset=True, db=db)

        # In seed.py: Gardenia Classic White Bread active batch expires in today + 2 days
        bread = db.query(Product).filter(Product.name == "Gardenia Classic White Bread").first()
        active_batch = (
            db.query(InventoryBatch)
            .filter(InventoryBatch.product_id == bread.id, InventoryBatch.remaining_quantity > 0)
            .first()
        )
        assert active_batch is not None
        # PHT today is 2026-09-23 -> today + 2d = 2026-09-25
        assert active_batch.expiration_date == date(2026, 9, 25)
