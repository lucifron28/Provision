from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.time import household_today
from app.models.batch import InventoryBatch
from app.models.event import InventoryEvent
from app.models.session import GrocerySession
from app.models.shopping import ShoppingListItem


def _register_and_login(client, label: str) -> dict:
    email = f"{label}-{uuid4().hex}@provision.test"
    password = "P0-household-test-password"
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": label},
    )
    assert registered.status_code == 201, registered.text

    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    profile = client.get("/api/v1/auth/me", headers=headers)
    assert profile.status_code == 200, profile.text
    memberships = client.get("/api/v1/households/", headers=headers)
    assert memberships.status_code == 200, memberships.text
    defaults = [row for row in memberships.json() if row["is_default"]]
    assert len(defaults) == 1
    return {
        "email": email,
        "headers": headers,
        "id": profile.json()["id"],
        "household_id": defaults[0]["id"],
    }


@pytest.fixture
def two_accounts(unauthed_client):
    return (
        _register_and_login(unauthed_client, "north"),
        _register_and_login(unauthed_client, "south"),
    )


def _create_pantry(
    client,
    account: dict,
    label: str,
    *,
    barcode: str,
    idempotency_key: str,
    stock: float,
    unit_price: str,
    total_amount: str,
    waste_quantity: float,
    waste_price: str,
) -> dict:
    headers = account["headers"]
    product = client.post(
        "/api/v1/products/",
        headers=headers,
        json={
            "name": f"{label} staple",
            "barcode": barcode,
            "brand": f"{label} brand",
            "category": "Pantry",
            "unit": "kg",
        },
    )
    assert product.status_code == 201, product.text
    product = product.json()

    low_stock_product = client.post(
        "/api/v1/products/",
        headers=headers,
        json={"name": f"{label} low stock", "unit": "items"},
    )
    assert low_stock_product.status_code == 201, low_stock_product.text
    low_stock_product = low_stock_product.json()

    waste_product = client.post(
        "/api/v1/products/",
        headers=headers,
        json={"name": f"{label} waste", "unit": "items"},
    )
    assert waste_product.status_code == 201, waste_product.text
    waste_product = waste_product.json()

    location = client.post(
        "/api/v1/locations/",
        headers=headers,
        json={"name": f"{label} pantry", "description": f"{label} shelf"},
    )
    assert location.status_code == 201, location.text
    location = location.json()

    session_body = {
        "store_name": f"{label} market",
        "idempotency_key": idempotency_key,
    }
    session = client.post(
        "/api/v1/grocery-sessions/", headers=headers, json=session_body
    )
    assert session.status_code == 201, session.text
    session = session.json()
    retry = client.post(
        "/api/v1/grocery-sessions/", headers=headers, json=session_body
    )
    assert retry.status_code == 201, retry.text
    assert retry.json()["id"] == session["id"]

    expires = (household_today() + timedelta(days=3)).isoformat()
    committed = client.post(
        f"/api/v1/grocery-sessions/{session['id']}/commit",
        headers=headers,
        json={
            "items": [
                {
                    "product_id": product["id"],
                    "storage_location_id": location["id"],
                    "quantity": stock,
                    "unit_price": unit_price,
                    "expiration_date": expires,
                }
            ],
            "total_amount": total_amount,
        },
    )
    assert committed.status_code == 200, committed.text
    active_batch = committed.json()["batches"][0]

    waste_batch_response = client.post(
        "/api/v1/batches/",
        headers=headers,
        json={
            "product_id": waste_product["id"],
            "storage_location_id": location["id"],
            "grocery_session_id": session["id"],
            "expiration_date": (household_today() + timedelta(days=4)).isoformat(),
            "original_quantity": waste_quantity,
            "unit_price": waste_price,
        },
    )
    assert waste_batch_response.status_code == 201, waste_batch_response.text
    waste_batch = waste_batch_response.json()
    discarded = client.post(
        f"/api/v1/inventory/batches/{waste_batch['id']}/discard",
        headers=headers,
        json={"reason": f"{label} waste"},
    )
    assert discarded.status_code == 200, discarded.text

    shopping_item = client.post(
        "/api/v1/shopping-list/",
        headers=headers,
        json={
            "product_id": product["id"],
            "name": f"{label} list item",
            "quantity": 2,
        },
    )
    assert shopping_item.status_code == 201, shopping_item.text

    return {
        "idempotency_key": idempotency_key,
        "product": product,
        "low_stock_product": low_stock_product,
        "waste_product": waste_product,
        "location": location,
        "session": session,
        "active_batch": active_batch,
        "waste_batch": waste_batch,
        "shopping_item": shopping_item.json(),
    }


def _seed_pair(client, north, south):
    idempotency_key = str(uuid4())
    north_data = _create_pantry(
        client,
        north,
        "North",
        barcode="shared-household-barcode",
        idempotency_key=idempotency_key,
        stock=6,
        unit_price="3.50",
        total_amount="25.00",
        waste_quantity=2,
        waste_price="2.50",
    )
    south_data = _create_pantry(
        client,
        south,
        "South",
        barcode="shared-household-barcode",
        idempotency_key=idempotency_key,
        stock=30,
        unit_price="100.00",
        total_amount="900.00",
        waste_quantity=3,
        waste_price="10.00",
    )
    return north_data, south_data


def test_seven_router_lists_and_all_analytics_are_household_scoped(
    unauthed_client, two_accounts
):
    north, south = two_accounts
    north_data, south_data = _seed_pair(unauthed_client, north, south)
    headers = north["headers"]

    product_list = unauthed_client.get("/api/v1/products/", headers=headers)
    assert product_list.status_code == 200
    assert {row["name"] for row in product_list.json()} == {
        "North staple",
        "North low stock",
        "North waste",
    }
    barcode = unauthed_client.get(
        "/api/v1/products/barcode/shared-household-barcode", headers=headers
    )
    south_barcode = unauthed_client.get(
        "/api/v1/products/barcode/shared-household-barcode",
        headers=south["headers"],
    )
    assert barcode.json()["id"] == north_data["product"]["id"]
    assert south_barcode.json()["id"] == south_data["product"]["id"]
    assert barcode.json()["id"] != south_barcode.json()["id"]
    duplicate_barcode = unauthed_client.post(
        "/api/v1/products/",
        headers=headers,
        json={"name": "North duplicate", "barcode": "shared-household-barcode"},
    )
    assert duplicate_barcode.status_code == 400

    locations = unauthed_client.get("/api/v1/locations/", headers=headers)
    assert locations.status_code == 200
    assert {row["name"] for row in locations.json()} == {"North pantry"}

    sessions = unauthed_client.get("/api/v1/grocery-sessions/", headers=headers)
    assert sessions.status_code == 200
    assert [(row["id"], row["store_name"]) for row in sessions.json()] == [
        (north_data["session"]["id"], "North market")
    ]
    assert north_data["session"]["id"] != south_data["session"]["id"]
    assert north_data["idempotency_key"] == south_data["idempotency_key"]
    key_conflict = unauthed_client.post(
        "/api/v1/grocery-sessions/",
        headers=headers,
        json={
            "store_name": "North changed payload",
            "idempotency_key": north_data["idempotency_key"],
        },
    )
    assert key_conflict.status_code == 409

    batches = unauthed_client.get("/api/v1/batches/", headers=headers)
    assert batches.status_code == 200
    assert [row["id"] for row in batches.json()] == [north_data["active_batch"]["id"]]

    events = unauthed_client.get("/api/v1/inventory/events", headers=headers)
    assert events.status_code == 200
    assert {row["batch_id"] for row in events.json()} == {
        north_data["active_batch"]["id"],
        north_data["waste_batch"]["id"],
    }

    shopping = unauthed_client.get("/api/v1/shopping-list/", headers=headers)
    assert shopping.status_code == 200
    assert [row["name"] for row in shopping.json()] == ["North list item"]

    summary = unauthed_client.get("/api/v1/analytics/inventory-summary", headers=headers)
    expiring = unauthed_client.get(
        "/api/v1/analytics/expiring-soon?days=7", headers=headers
    )
    low_stock = unauthed_client.get(
        "/api/v1/analytics/low-stock?threshold=1", headers=headers
    )
    valuation = unauthed_client.get("/api/v1/analytics/valuation", headers=headers)
    spending = unauthed_client.get("/api/v1/analytics/spending", headers=headers)
    waste = unauthed_client.get("/api/v1/analytics/waste", headers=headers)
    price_history = unauthed_client.get(
        f"/api/v1/analytics/price-history/{north_data['product']['id']}",
        headers=headers,
    )
    analytics_responses = [
        summary,
        expiring,
        low_stock,
        valuation,
        spending,
        waste,
        price_history,
    ]
    assert [response.status_code for response in analytics_responses] == [200] * 7
    assert {row["product_name"] for row in summary.json()} == {"North staple"}
    assert {row["product_name"] for row in expiring.json()} == {"North staple"}
    assert {row["product_name"] for row in low_stock.json()} == {
        "North low stock",
        "North waste",
    }
    assert Decimal(valuation.json()["total_value"]) == Decimal("21.00")
    assert valuation.json()["total_active_batches"] == 1
    assert valuation.json()["total_active_products"] == 1
    assert Decimal(spending.json()["total_spent"]) == Decimal("25.00")
    assert spending.json()["sessions_count"] == 1
    assert waste.json()["total_waste_events"] == 1
    assert waste.json()["total_quantity_wasted"] == 2
    assert Decimal(waste.json()["total_financial_loss"]) == Decimal("5.00")
    assert waste.json()["wasted_items"][0]["product_name"] == "North waste"
    assert price_history.json()["product_name"] == "North staple"
    assert len(price_history.json()["price_points"]) == 1
    assert price_history.json()["price_points"][0]["store_name"] == "North market"

    for response in [product_list, locations, sessions, batches, events, shopping, *analytics_responses]:
        assert "South" not in response.text


def test_foreign_ids_cannot_be_read_or_mutated_and_owner_data_stays_unchanged(
    unauthed_client, two_accounts
):
    north, south = two_accounts
    north_data, south_data = _seed_pair(unauthed_client, north, south)
    headers = north["headers"]
    foreign_product = south_data["product"]["id"]
    foreign_location = south_data["location"]["id"]
    foreign_batch = south_data["active_batch"]["id"]
    foreign_waste_batch = south_data["waste_batch"]["id"]
    foreign_session = south_data["session"]["id"]
    foreign_item = south_data["shopping_item"]["id"]
    south_events_before = unauthed_client.get(
        "/api/v1/inventory/events", headers=south["headers"]
    ).json()

    guessed = [
        unauthed_client.get(f"/api/v1/products/{foreign_product}", headers=headers),
        unauthed_client.patch(
            f"/api/v1/products/{foreign_product}",
            headers=headers,
            json={"name": "stolen product"},
        ),
        unauthed_client.delete(f"/api/v1/products/{foreign_product}", headers=headers),
        unauthed_client.get(f"/api/v1/locations/{foreign_location}", headers=headers),
        unauthed_client.patch(
            f"/api/v1/locations/{foreign_location}",
            headers=headers,
            json={"name": "stolen location"},
        ),
        unauthed_client.delete(f"/api/v1/locations/{foreign_location}", headers=headers),
        unauthed_client.get(f"/api/v1/batches/{foreign_batch}", headers=headers),
        unauthed_client.patch(
            f"/api/v1/batches/{foreign_batch}",
            headers=headers,
            json={"unit_price": "0.01"},
        ),
        unauthed_client.delete(f"/api/v1/batches/{foreign_batch}", headers=headers),
        unauthed_client.post(
            f"/api/v1/inventory/batches/{foreign_waste_batch}/discard",
            headers=headers,
            json={"reason": "stolen discard"},
        ),
        unauthed_client.post(
            f"/api/v1/inventory/batches/{foreign_batch}/adjust",
            headers=headers,
            json={"new_remaining_quantity": 0, "reason": "stolen adjustment"},
        ),
        unauthed_client.post(
            "/api/v1/inventory/consume",
            headers=headers,
            json={"product_id": foreign_product, "quantity": 1},
        ),
        unauthed_client.get(
            f"/api/v1/inventory/events?batch_id={foreign_batch}", headers=headers
        ),
        unauthed_client.get(f"/api/v1/grocery-sessions/{foreign_session}", headers=headers),
        unauthed_client.patch(
            f"/api/v1/grocery-sessions/{foreign_session}",
            headers=headers,
            json={"notes": "stolen edit"},
        ),
        unauthed_client.post(
            f"/api/v1/grocery-sessions/{foreign_session}/commit",
            headers=headers,
            json={"items": []},
        ),
        unauthed_client.delete(
            f"/api/v1/grocery-sessions/{foreign_session}", headers=headers
        ),
        unauthed_client.get(f"/api/v1/shopping-list/{foreign_item}", headers=headers),
        unauthed_client.patch(
            f"/api/v1/shopping-list/{foreign_item}",
            headers=headers,
            json={"name": "stolen item"},
        ),
        unauthed_client.post(
            f"/api/v1/shopping-list/{foreign_item}/toggle", headers=headers
        ),
        unauthed_client.delete(f"/api/v1/shopping-list/{foreign_item}", headers=headers),
    ]
    assert [response.status_code for response in guessed] == [404] * 12 + [200] + [404] * 8
    assert guessed[12].json() == []
    foreign_price_history = unauthed_client.get(
        f"/api/v1/analytics/price-history/{foreign_product}", headers=headers
    )
    assert foreign_price_history.status_code == 404

    cross_product_item = unauthed_client.post(
        "/api/v1/shopping-list/",
        headers=headers,
        json={"product_id": foreign_product, "quantity": 1},
    )
    assert cross_product_item.status_code == 404
    cross_product_batch = unauthed_client.post(
        "/api/v1/batches/",
        headers=headers,
        json={"product_id": foreign_product, "original_quantity": 1},
    )
    assert cross_product_batch.status_code == 404
    forged_household = unauthed_client.get(
        "/api/v1/products/",
        headers={**headers, "X-Household-ID": str(south["household_id"])},
    )
    assert forged_household.status_code == 403

    south_headers = south["headers"]
    assert unauthed_client.get(
        f"/api/v1/products/{foreign_product}", headers=south_headers
    ).json()["name"] == "South staple"
    assert unauthed_client.get(
        f"/api/v1/locations/{foreign_location}", headers=south_headers
    ).json()["name"] == "South pantry"
    assert unauthed_client.get(
        f"/api/v1/batches/{foreign_batch}", headers=south_headers
    ).json()["remaining_quantity"] == 30
    assert unauthed_client.get(
        f"/api/v1/grocery-sessions/{foreign_session}", headers=south_headers
    ).json()["status"] == "COMPLETED"
    assert unauthed_client.get(
        f"/api/v1/shopping-list/{foreign_item}", headers=south_headers
    ).json()["is_bought"] is False
    assert unauthed_client.get(
        "/api/v1/inventory/events", headers=south_headers
    ).json() == south_events_before

    north_product = unauthed_client.get(
        f"/api/v1/products/{north_data['product']['id']}", headers=headers
    )
    assert north_product.status_code == 200
    assert north_product.json()["name"] == "North staple"


def test_cross_household_commit_and_database_composite_foreign_keys_are_atomic(
    unauthed_client, db, two_accounts
):
    north, south = two_accounts
    north_data, south_data = _seed_pair(unauthed_client, north, south)
    headers = north["headers"]
    draft = unauthed_client.post(
        "/api/v1/grocery-sessions/",
        headers=headers,
        json={"store_name": "North atomic draft"},
    )
    assert draft.status_code == 201, draft.text
    draft_id = draft.json()["id"]
    batch_count_before = db.scalar(select(func.count(InventoryBatch.id)))
    event_count_before = db.scalar(select(func.count(InventoryEvent.id)))

    mixed_commit = unauthed_client.post(
        f"/api/v1/grocery-sessions/{draft_id}/commit",
        headers=headers,
        json={
            "items": [
                {"product_id": north_data["product"]["id"], "quantity": 1},
                {"product_id": south_data["product"]["id"], "quantity": 2},
            ]
        },
    )
    assert mixed_commit.status_code == 404
    assert db.scalar(select(func.count(InventoryBatch.id))) == batch_count_before
    assert db.scalar(select(func.count(InventoryEvent.id))) == event_count_before
    assert unauthed_client.get(
        f"/api/v1/grocery-sessions/{draft_id}", headers=headers
    ).json()["status"] == "DRAFT"

    household_id = north["household_id"]
    product_id = north_data["product"]["id"]
    location_id = north_data["location"]["id"]
    session_id = north_data["session"]["id"]
    foreign_product_id = south_data["product"]["id"]
    foreign_location_id = south_data["location"]["id"]
    foreign_session_id = south_data["session"]["id"]

    malformed_batches = [
        InventoryBatch(
            household_id=household_id,
            product_id=foreign_product_id,
            storage_location_id=location_id,
            grocery_session_id=session_id,
            original_quantity=1,
            remaining_quantity=1,
        ),
        InventoryBatch(
            household_id=household_id,
            product_id=product_id,
            storage_location_id=foreign_location_id,
            grocery_session_id=session_id,
            original_quantity=1,
            remaining_quantity=1,
        ),
        InventoryBatch(
            household_id=household_id,
            product_id=product_id,
            storage_location_id=location_id,
            grocery_session_id=foreign_session_id,
            original_quantity=1,
            remaining_quantity=1,
        ),
    ]
    for malformed in malformed_batches:
        db.add(malformed)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
        assert db.scalar(select(func.count(InventoryBatch.id))) == batch_count_before
        assert db.scalar(select(func.count(InventoryEvent.id))) == event_count_before

    shopping_count_before = db.scalar(select(func.count(ShoppingListItem.id)))
    db.add(
        ShoppingListItem(
            household_id=household_id,
            product_id=foreign_product_id,
            name="invalid cross-household relation",
            quantity=1,
            is_bought=False,
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
    assert db.scalar(select(func.count(ShoppingListItem.id))) == shopping_count_before


def test_shared_member_access_role_guards_and_default_rotation(unauthed_client, two_accounts):
    north, south = two_accounts
    north_product = unauthed_client.post(
        "/api/v1/products/",
        headers=north["headers"],
        json={"name": "Shared North Pantry"},
    )
    assert north_product.status_code == 201

    add_member = unauthed_client.post(
        "/api/v1/households/current/members",
        headers=north["headers"],
        json={"user_id": south["id"], "role": "MEMBER"},
    )
    assert add_member.status_code == 201, add_member.text
    assert add_member.json()["is_default"] is False

    selected = unauthed_client.get(
        "/api/v1/households/current",
        headers={
            **south["headers"],
            "X-Household-ID": str(north["household_id"]),
        },
    )
    assert selected.status_code == 200
    assert selected.json()["role"] == "MEMBER"
    shared_products = unauthed_client.get(
        "/api/v1/products/",
        headers={
            **south["headers"],
            "X-Household-ID": str(north["household_id"]),
        },
    )
    assert [row["name"] for row in shared_products.json()] == ["Shared North Pantry"]

    forbidden = [
        unauthed_client.post(
            "/api/v1/households/current/members",
            headers={
                **south["headers"],
                "X-Household-ID": str(north["household_id"]),
            },
            json={"user_id": south["id"], "role": "OWNER"},
        ),
        unauthed_client.patch(
            f"/api/v1/households/current/members/{south['id']}",
            headers={
                **south["headers"],
                "X-Household-ID": str(north["household_id"]),
            },
            json={"role": "OWNER"},
        ),
        unauthed_client.delete(
            f"/api/v1/households/current/members/{north['id']}",
            headers={
                **south["headers"],
                "X-Household-ID": str(north["household_id"]),
            },
        ),
    ]
    assert [response.status_code for response in forbidden] == [403, 403, 403]

    leave_default = unauthed_client.delete(
        f"/api/v1/households/current/members/{south['id']}",
        headers=south["headers"],
    )
    assert leave_default.status_code == 204
    south_households = unauthed_client.get("/api/v1/households/", headers=south["headers"])
    assert south_households.status_code == 200
    assert south_households.json() == [
        {
            "id": north["household_id"],
            "name": "Home",
            "role": "MEMBER",
            "is_default": True,
        }
    ]
    assert unauthed_client.get(
        "/api/v1/products/", headers=south["headers"]
    ).status_code == 200

    remove_member = unauthed_client.delete(
        f"/api/v1/households/current/members/{south['id']}",
        headers=north["headers"],
    )
    assert remove_member.status_code == 204
    assert unauthed_client.get(
        "/api/v1/products/",
        headers={
            **south["headers"],
            "X-Household-ID": str(north["household_id"]),
        },
    ).status_code == 403
    assert unauthed_client.get("/api/v1/households/", headers=south["headers"]).json() == []
    assert unauthed_client.get("/api/v1/products/", headers=north["headers"]).status_code == 200


def test_bulk_shopping_routes_only_touch_the_callers_household(
    unauthed_client, two_accounts
):
    north, south = two_accounts
    north_data, south_data = _seed_pair(unauthed_client, north, south)

    north_bought = unauthed_client.post(
        f"/api/v1/shopping-list/{north_data['shopping_item']['id']}/toggle",
        headers=north["headers"],
    )
    south_bought = unauthed_client.post(
        f"/api/v1/shopping-list/{south_data['shopping_item']['id']}/toggle",
        headers=south["headers"],
    )
    assert north_bought.status_code == south_bought.status_code == 200
    assert north_bought.json()["is_bought"] is True
    assert south_bought.json()["is_bought"] is True

    generated = unauthed_client.post(
        "/api/v1/shopping-list/generate-from-low-stock",
        headers=north["headers"],
        json={"threshold": 1},
    )
    assert generated.status_code == 200, generated.text
    assert {row["name"] for row in generated.json()} == {
        "North low stock",
        "North waste",
    }
    assert all(row["name"].startswith("North ") for row in generated.json())

    cleared = unauthed_client.delete(
        "/api/v1/shopping-list/completed/clear", headers=north["headers"]
    )
    assert cleared.status_code == 200
    assert cleared.json()["message"] == "Successfully removed 1 completed item(s)"

    north_items = unauthed_client.get(
        "/api/v1/shopping-list/", headers=north["headers"]
    )
    south_items = unauthed_client.get(
        "/api/v1/shopping-list/", headers=south["headers"]
    )
    assert {row["name"] for row in north_items.json()} == {
        "North low stock",
        "North waste",
    }
    assert all(row["is_bought"] is False for row in north_items.json())
    assert [row["name"] for row in south_items.json()] == ["South list item"]
    assert south_items.json()[0]["is_bought"] is True


def test_cross_household_locations_are_rejected_by_batch_and_session_routes(
    unauthed_client, db, two_accounts
):
    north, south = two_accounts
    north_data, south_data = _seed_pair(unauthed_client, north, south)
    headers = north["headers"]
    batch_count_before = db.scalar(select(func.count(InventoryBatch.id)))
    event_count_before = db.scalar(select(func.count(InventoryEvent.id)))

    cross_location_batch = unauthed_client.post(
        "/api/v1/batches/",
        headers=headers,
        json={
            "product_id": north_data["product"]["id"],
            "storage_location_id": south_data["location"]["id"],
            "original_quantity": 1,
        },
    )
    assert cross_location_batch.status_code == 404

    cross_location_update = unauthed_client.patch(
        f"/api/v1/batches/{north_data['active_batch']['id']}",
        headers=headers,
        json={"storage_location_id": south_data["location"]["id"]},
    )
    assert cross_location_update.status_code == 404

    draft = unauthed_client.post(
        "/api/v1/grocery-sessions/",
        headers=headers,
        json={"store_name": "North wrong-location draft"},
    )
    assert draft.status_code == 201, draft.text
    wrong_location_commit = unauthed_client.post(
        f"/api/v1/grocery-sessions/{draft.json()['id']}/commit",
        headers=headers,
        json={
            "items": [
                {
                    "product_id": north_data["product"]["id"],
                    "storage_location_id": south_data["location"]["id"],
                    "quantity": 1,
                }
            ]
        },
    )
    assert wrong_location_commit.status_code == 404
    assert unauthed_client.get(
        f"/api/v1/grocery-sessions/{draft.json()['id']}", headers=headers
    ).json()["status"] == "DRAFT"

    north_batch = unauthed_client.get(
        f"/api/v1/batches/{north_data['active_batch']['id']}", headers=headers
    )
    assert north_batch.status_code == 200
    assert north_batch.json()["storage_location_id"] == north_data["location"]["id"]
    assert north_batch.json()["remaining_quantity"] == 6
    assert db.scalar(select(func.count(InventoryBatch.id))) == batch_count_before
    assert db.scalar(select(func.count(InventoryEvent.id))) == event_count_before

    south_batch = unauthed_client.get(
        f"/api/v1/batches/{south_data['active_batch']['id']}",
        headers=south["headers"],
    )
    assert south_batch.status_code == 200
    assert south_batch.json()["storage_location_id"] == south_data["location"]["id"]
    assert south_batch.json()["remaining_quantity"] == 30
    south_location = unauthed_client.get(
        f"/api/v1/locations/{south_data['location']['id']}",
        headers=south["headers"],
    )
    assert south_location.status_code == 200
    assert south_location.json()["name"] == "South pantry"
