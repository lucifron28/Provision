from datetime import datetime, timezone

from app.models.product import Product
from app.models.location import StorageLocation
from app.models.batch import InventoryBatch
from app.models.shopping import ShoppingListItem


def test_household_pagination_is_stable_with_equal_sort_keys(client, db, auth_household):
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    products = [Product(household_id=auth_household.id, name="Rice") for _ in range(135)]
    locations = [StorageLocation(household_id=auth_household.id, name=f"Shelf {i:03d}") for i in range(135)]
    shopping = [ShoppingListItem(household_id=auth_household.id, name="Eggs", quantity=1,
                is_bought=False, created_at=timestamp, updated_at=timestamp) for _ in range(135)]
    db.add_all(products + locations + shopping)
    db.flush()
    batches = [InventoryBatch(household_id=auth_household.id, product_id=product.id,
               original_quantity=1, remaining_quantity=1, purchased_at=timestamp) for product in products]
    db.add_all(batches)
    db.commit()
    expected_products = sorted(item.id for item in products)
    expected_shopping = sorted(item.id for item in shopping)
    expected_locations = [item.id for item in locations]
    expected_batches = sorted(item.id for item in batches)

    def read_all(path):
        result = []
        for offset in (0, 100):
            response = client.get(path, params={"skip": offset, "limit": 100})
            assert response.status_code == 200, response.text
            result.extend(row["id"] for row in response.json())
        return result

    assert read_all("/api/v1/products/") == expected_products
    assert read_all("/api/v1/locations/") == expected_locations
    assert read_all("/api/v1/batches/") == expected_batches
    assert read_all("/api/v1/shopping-list/") == expected_shopping
