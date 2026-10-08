"""
Cache safety, token isolation, session separation, and partial query tests.

Verifies:
1. Cache isolation:
   - Invalid or forged JWT tokens return 401 Unauthorized across all protected endpoints.
   - Expired JWT tokens return 401 Unauthorized across all protected endpoints.
   - Missing Authorization headers return 401 Unauthorized across all protected endpoints.
   - Malformed Authorization headers return 401 Unauthorized.

2. User logout / session separation:
   - Deactivated user tokens are rejected with 401 Unauthorized.
   - Deleted / non-existent user tokens are rejected with 401 Unauthorized.
   - Token from one user session cannot access protected endpoints once invalidated,
     while another active user's session remains unaffected.

3. Partial query safety:
   - Category filtering (e.g. ?category=Dairy) returns subsets without modifying canonical records.
   - Search filtering (e.g. ?search=Tuna) returns subsets without modifying canonical records.
   - Zero-match filtering returns an empty list without dropping or altering canonical records.
   - Batch filtering by product_id returns subsets without affecting other products' batches.
"""

from datetime import timedelta, date
from decimal import Decimal
import pytest
from sqlalchemy import select, func

from app.core.security import create_access_token, hash_password
from app.models.user import User
from app.models.product import Product
from app.models.batch import InventoryBatch
from app.models.location import StorageLocation


# ============================================================================
# 1. Cache Isolation Tests: Token Validation on Protected Endpoints
# ============================================================================

def test_missing_token_rejects_protected_pantry_endpoints(unauthed_client):
    """
    Cache isolation invariant:
    Requests without auth credentials must be rejected with 401 across all
    household pantry endpoints, ensuring unauthenticated clients are never
    served protected data.
    """
    endpoints = [
        "/api/v1/products/",
        "/api/v1/locations/",
        "/api/v1/batches/",
        "/api/v1/shopping-list/",
        "/api/v1/grocery-sessions/",
        "/api/v1/analytics/inventory-summary",
    ]
    for ep in endpoints:
        resp = unauthed_client.get(ep)
        assert resp.status_code == 401, f"Endpoint {ep} did not reject unauthenticated access"
        detail = resp.json().get("detail", "").lower()
        assert "not authenticated" in detail or "credentials" in detail


def test_invalid_token_rejects_protected_pantry_endpoints(unauthed_client):
    """
    Cache isolation invariant:
    Requests with an invalid or forged JWT token must return 401 Unauthorized,
    preventing any fallback to cached protected data.
    """
    bad_headers = {"Authorization": "Bearer invalid.jwt.token"}
    endpoints = [
        "/api/v1/products/",
        "/api/v1/locations/",
        "/api/v1/batches/",
        "/api/v1/shopping-list/",
        "/api/v1/grocery-sessions/",
        "/api/v1/analytics/inventory-summary",
    ]
    for ep in endpoints:
        resp = unauthed_client.get(ep, headers=bad_headers)
        assert resp.status_code == 401, f"Endpoint {ep} did not return 401 for invalid token"
        assert "could not validate credentials" in resp.json()["detail"].lower()


def test_expired_token_rejects_protected_pantry_endpoints(unauthed_client, auth_user):
    """
    Cache isolation invariant:
    Requests with an expired JWT token must be rejected with 401 Unauthorized,
    ensuring expired sessions cannot access live or cached pantry data.
    """
    expired_token = create_access_token(
        subject=auth_user.email,
        expires_delta=timedelta(seconds=-30),  # expired 30s ago
    )
    expired_headers = {"Authorization": f"Bearer {expired_token}"}
    endpoints = [
        "/api/v1/products/",
        "/api/v1/locations/",
        "/api/v1/batches/",
        "/api/v1/shopping-list/",
        "/api/v1/grocery-sessions/",
        "/api/v1/analytics/inventory-summary",
    ]
    for ep in endpoints:
        resp = unauthed_client.get(ep, headers=expired_headers)
        assert resp.status_code == 401, f"Endpoint {ep} did not return 401 for expired token"
        assert "could not validate credentials" in resp.json()["detail"].lower()


def test_malformed_token_header_rejects_access(unauthed_client):
    """
    Cache isolation invariant:
    Requests with malformed authorization headers must be rejected with 401.
    """
    malformed_headers = [
        {"Authorization": "Basic dXNlcjpwYXNz"},
        {"Authorization": "Token 1234567890"},
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer   "},
    ]
    for headers in malformed_headers:
        resp = unauthed_client.get("/api/v1/products/", headers=headers)
        assert resp.status_code == 401


# ============================================================================
# 2. User Logout & Session Separation Tests
# ============================================================================

def test_deactivated_user_token_rejected_on_pantry_endpoints(db, unauthed_client, auth_user):
    """
    Session safety invariant:
    When a user session is terminated or the user is marked inactive (e.g. deactivated account),
    their existing token MUST return 401 on protected pantry endpoints.
    """
    valid_token = create_access_token(subject=auth_user.email)
    headers = {"Authorization": f"Bearer {valid_token}"}

    # Verify access works while active
    resp_active = unauthed_client.get("/api/v1/products/", headers=headers)
    assert resp_active.status_code == 200

    # Simulate account deactivation / session revocation
    auth_user.is_active = False
    db.commit()

    # Verify access is immediately rejected with 401
    resp_deactivated = unauthed_client.get("/api/v1/products/", headers=headers)
    assert resp_deactivated.status_code == 401
    assert "inactive" in resp_deactivated.json()["detail"].lower()

    # Verify other endpoints are also blocked
    resp_loc = unauthed_client.get("/api/v1/locations/", headers=headers)
    assert resp_loc.status_code == 401

    resp_batches = unauthed_client.get("/api/v1/batches/", headers=headers)
    assert resp_batches.status_code == 401


def test_deleted_user_token_rejected_on_pantry_endpoints(db, unauthed_client):
    """
    Session safety invariant:
    A JWT whose subject refers to a user that was deleted or no longer exists in DB
    must return 401 'User no longer exists'.
    """
    temp_user = User(
        email="temporary@provision.local",
        hashed_password=hash_password("temppass123"),
        display_name="Temp User",
        is_active=True,
    )
    db.add(temp_user)
    db.commit()
    db.refresh(temp_user)

    token = create_access_token(subject=temp_user.email)
    headers = {"Authorization": f"Bearer {token}"}

    # Verify access works before deletion
    resp_before = unauthed_client.get("/api/v1/products/", headers=headers)
    assert resp_before.status_code == 200

    # Delete the user record
    db.delete(temp_user)
    db.commit()

    # Token must now be rejected with 401
    resp_after = unauthed_client.get("/api/v1/products/", headers=headers)
    assert resp_after.status_code == 401
    assert "not found" in resp_after.json()["detail"].lower()


def test_session_separation_between_distinct_users(db, unauthed_client, auth_user):
    """
    Session separation invariant:
    User A and User B maintain distinct authentication contexts.
    Invalidating User A's session must not allow User A access, while User B
    continues to have access with their valid session.
    """
    user_b = User(
        email="user_b@provision.local",
        hashed_password=hash_password("userbpass123"),
        display_name="User B",
        is_active=True,
    )
    db.add(user_b)
    db.commit()
    db.refresh(user_b)

    token_a = create_access_token(subject=auth_user.email)
    token_b = create_access_token(subject=user_b.email)

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Both users can access pantry data
    assert unauthed_client.get("/api/v1/products/", headers=headers_a).status_code == 200
    assert unauthed_client.get("/api/v1/products/", headers=headers_b).status_code == 200

    # Deactivate User A
    auth_user.is_active = False
    db.commit()

    # User A is now rejected
    assert unauthed_client.get("/api/v1/products/", headers=headers_a).status_code == 401

    # User B remains active and authorized
    assert unauthed_client.get("/api/v1/products/", headers=headers_b).status_code == 200


# ============================================================================
# 3. Partial Query Safety Tests: Preservation of Canonical Data
# ============================================================================

def test_partial_query_safety_category_filtering(db, client):
    """
    Partial query safety invariant:
    Filtering products by category must return only the matching subset and
    must NOT modify, delete, or truncate canonical database records.
    """
    # 1. Seed 4 products across 2 categories
    products_payload = [
        {"name": "Century Tuna Flakes in Oil", "brand": "Century", "category": "Canned Goods"},
        {"name": "San Marino Corned Tuna", "brand": "San Marino", "category": "Canned Goods"},
        {"name": "Magnolia Fresh Milk", "brand": "Magnolia", "category": "Dairy"},
        {"name": "Alaska Evaporated Milk", "brand": "Alaska", "category": "Dairy"},
    ]
    created_ids = []
    for payload in products_payload:
        res = client.post("/api/v1/products/", json=payload)
        assert res.status_code == 201
        created_ids.append(res.json()["id"])

    # Baseline: verify 4 canonical products in DB
    total_in_db = db.scalar(select(func.count(Product.id)))
    assert total_in_db == 4

    # 2. Filter by Dairy category
    res_dairy = client.get("/api/v1/products/?category=Dairy")
    assert res_dairy.status_code == 200
    dairy_items = res_dairy.json()
    assert len(dairy_items) == 2
    assert all(item["category"] == "Dairy" for item in dairy_items)

    # Invariant: DB must still contain all 4 canonical products
    db_after_dairy = db.scalar(select(func.count(Product.id)))
    assert db_after_dairy == 4

    # 3. Filter by Canned Goods category
    res_canned = client.get("/api/v1/products/?category=Canned Goods")
    assert res_canned.status_code == 200
    canned_items = res_canned.json()
    assert len(canned_items) == 2
    assert all(item["category"] == "Canned Goods" for item in canned_items)

    # Invariant: DB count untouched
    assert db.scalar(select(func.count(Product.id))) == 4

    # 4. Unfiltered query returns complete canonical set
    res_all = client.get("/api/v1/products/")
    assert res_all.status_code == 200
    all_items = res_all.json()
    assert len(all_items) == 4
    all_names = {item["name"] for item in all_items}
    assert all_names == {p["name"] for p in products_payload}


def test_partial_query_safety_search_filtering(db, client):
    """
    Partial query safety invariant:
    Searching by keyword (including zero-match queries) returns matching subsets
    without altering or dropping canonical records in the database.
    """
    # 1. Seed products
    products = [
        {"name": "Doña Maria Jasponica Rice", "brand": "Doña Maria", "category": "Grains"},
        {"name": "Datu Puti Soy Sauce", "brand": "Datu Puti", "category": "Condiments"},
        {"name": "Datu Puti Vinegar", "brand": "Datu Puti", "category": "Condiments"},
        {"name": "Silver Swan Soy Sauce", "brand": "Silver Swan", "category": "Condiments"},
    ]
    for p in products:
        res = client.post("/api/v1/products/", json=p)
        assert res.status_code == 201

    assert db.scalar(select(func.count(Product.id))) == 4

    # 2. Search for 'Datu Puti' -> should return 2 items
    res_datu = client.get("/api/v1/products/?search=Datu")
    assert res_datu.status_code == 200
    datu_items = res_datu.json()
    assert len(datu_items) == 2
    assert all("Datu" in item["brand"] for item in datu_items)

    # Canonical DB count intact
    assert db.scalar(select(func.count(Product.id))) == 4

    # 3. Search for 'Soy Sauce' -> should return 2 items
    res_soy = client.get("/api/v1/products/?search=Soy")
    assert res_soy.status_code == 200
    assert len(res_soy.json()) == 2

    # Canonical DB count intact
    assert db.scalar(select(func.count(Product.id))) == 4

    # 4. Zero-match search -> should return empty list without touching DB
    res_zero = client.get("/api/v1/products/?search=NonExistentProductQueryXYZ987")
    assert res_zero.status_code == 200
    assert res_zero.json() == []

    # Invariant: DB still contains all 4 canonical products
    assert db.scalar(select(func.count(Product.id))) == 4
    res_unfiltered = client.get("/api/v1/products/")
    assert len(res_unfiltered.json()) == 4


def test_partial_query_safety_batches_filtering(db, client):
    """
    Partial query safety invariant:
    Querying batches filtered by product_id returns only batches for that product,
    leaving batches of other products completely intact in the database.
    """
    # 1. Setup location and 2 products
    loc_res = client.post("/api/v1/locations/", json={"name": "Kitchen Pantry"})
    assert loc_res.status_code == 201
    loc_id = loc_res.json()["id"]

    p1_res = client.post("/api/v1/products/", json={"name": "Product Alpha", "category": "Pantry"})
    p2_res = client.post("/api/v1/products/", json={"name": "Product Beta", "category": "Pantry"})
    p1_id = p1_res.json()["id"]
    p2_id = p2_res.json()["id"]

    # 2. Create 2 batches for Product 1
    exp1 = (date.today() + timedelta(days=20)).isoformat()
    client.post("/api/v1/batches/", json={
        "product_id": p1_id,
        "storage_location_id": loc_id,
        "original_quantity": 5.0,
        "unit_price": 50.0,
        "expiration_date": exp1,
    })
    client.post("/api/v1/batches/", json={
        "product_id": p1_id,
        "storage_location_id": loc_id,
        "original_quantity": 10.0,
        "unit_price": 50.0,
        "expiration_date": exp1,
    })

    # 3. Create 2 batches for Product 2
    exp2 = (date.today() + timedelta(days=40)).isoformat()
    client.post("/api/v1/batches/", json={
        "product_id": p2_id,
        "storage_location_id": loc_id,
        "original_quantity": 3.0,
        "unit_price": 100.0,
        "expiration_date": exp2,
    })
    client.post("/api/v1/batches/", json={
        "product_id": p2_id,
        "storage_location_id": loc_id,
        "original_quantity": 7.0,
        "unit_price": 100.0,
        "expiration_date": exp2,
    })

    # Total batches in DB must be 4
    total_batches = db.scalar(select(func.count(InventoryBatch.id)))
    assert total_batches == 4

    # 4. Filter batches by Product Alpha (p1_id)
    res_p1 = client.get(f"/api/v1/batches/?product_id={p1_id}")
    assert res_p1.status_code == 200
    p1_batches = res_p1.json()
    assert len(p1_batches) == 2
    assert all(b["product"]["id"] == p1_id for b in p1_batches)

    # Invariant: DB still contains all 4 batches
    assert db.scalar(select(func.count(InventoryBatch.id))) == 4

    # 5. Filter batches by Product Beta (p2_id)
    res_p2 = client.get(f"/api/v1/batches/?product_id={p2_id}")
    assert res_p2.status_code == 200
    p2_batches = res_p2.json()
    assert len(p2_batches) == 2
    assert all(b["product"]["id"] == p2_id for b in p2_batches)

    # Invariant: DB still contains all 4 batches
    assert db.scalar(select(func.count(InventoryBatch.id))) == 4

    # 6. Unfiltered batches query returns all 4 batches
    res_all_batches = client.get("/api/v1/batches/")
    assert res_all_batches.status_code == 200
    assert len(res_all_batches.json()) == 4
