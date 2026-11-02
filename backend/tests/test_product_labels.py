from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi import HTTPException
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.household import Household
from app.models.product import Product
from app.models.product_label import ProductAllergenLabel
from app.schemas.product_label import ProductLabelInput
from app.services.product_labels import write_label
from test_food_safety import catalog, declare, evaluate


def stock(client, catalog, name="garlic"):
    product = client.post("/api/v1/products/", json=dict(name=f"Test {name}", unit=catalog[name].default_unit)).json()
    mapping = dict(mode="DIRECT", ingredient_id=catalog[name].id, verified=True,
        unknown_composition=False, method="Reviewed ingredient identity")
    response = client.put(f"/api/v1/ingredients/products/{product['id']}/mapping", json=mapping)
    assert response.status_code == 200, response.text
    assert client.post("/api/v1/batches/", json=dict(product_id=product["id"], original_quantity=10)).status_code == 201
    return product, mapping


def label_payload(product, **kwargs):
    payload = dict(expected_mapping_version=1, reviewed=True, composition_known=True,
        expected_product_updated_at=product["updated_at"] if isinstance(product, dict) else product.updated_at.isoformat(),
        source_reference="Actual package ingredient/allergen declaration reviewed by member")
    payload.update(kwargs)
    return payload


def test_label_lifecycle_and_recreation_keep_revision_monotonic(client, db, catalog, auth_user):
    product, _ = stock(client, catalog)
    url = f"/api/v1/food-safety/products/{product['id']}/label"
    assert client.get(url).status_code == 404
    created = client.put(url, json=label_payload(product))
    assert created.status_code == 200, created.text
    assert created.headers["cache-control"] == "no-store"
    assert created.json()["reviewed_by_user_id"] == auth_user.id
    assert created.json()["current_for_product"] is True
    assert client.put(url, json=label_payload(product)).status_code == 409
    assert client.delete(url + "?expected_revision=2").status_code == 409
    assert client.delete(url + "?expected_revision=1").status_code == 204
    revoked = client.get(url).json()
    assert revoked["revoked"] is True and revoked["revision"] == 2
    assert revoked["current_for_product"] is False
    assert client.put(url, json=label_payload(product)).status_code == 409
    assert client.put(url, json=label_payload(product, expected_revision=1)).status_code == 409
    assert client.put(url, json=label_payload(product, expected_revision=2)).json()["revision"] == 3
    assert client.put(url, json=label_payload(product, expected_revision=1)).status_code == 409
    assert db.scalar(select(func.count()).select_from(ProductAllergenLabel)) == 3


@pytest.mark.parametrize("declared,possible,decision", [([], [], "eligible"), (["milk"], [], "blocked"), ([], ["milk"], "review_required")])
def test_label_declarations_gate_stock_backed_availability(client, catalog, declared, possible, decision):
    declare(client, "milk")
    product, _ = stock(client, catalog)
    assert evaluate(client, "garlic")["decision"] == "review_required"
    response = client.put(f"/api/v1/food-safety/products/{product['id']}/label",
        json=label_payload(product, declared_allergens=declared, possible_allergens=possible))
    assert response.status_code == 200
    result = evaluate(client, "garlic")
    assert result["decision"] == decision
    assert result["availability"]["overall_status"] == "full"


def test_product_or_mapping_changes_make_old_label_stale(client, catalog):
    declare(client)
    product, mapping = stock(client, catalog)
    url = f"/api/v1/food-safety/products/{product['id']}/label"
    assert client.put(url, json=label_payload(product)).status_code == 200
    assert evaluate(client, "garlic")["decision"] == "eligible"
    assert client.patch(f"/api/v1/products/{product['id']}", json=dict(brand="New formulation")).status_code == 200
    assert client.get(url).json()["current_for_product"] is False
    assert evaluate(client, "garlic")["decision"] == "review_required"
    assert client.put(url, json=label_payload(product, expected_revision=1)).status_code == 409
    product = client.patch(f"/api/v1/products/{product['id']}", json=dict(brand=None)).json()
    assert client.get(url).json()["current_for_product"] is False
    assert client.put(url, json=label_payload(product, expected_revision=1)).status_code == 200
    assert client.put(f"/api/v1/ingredients/products/{product['id']}/mapping",
        json={**mapping, "expected_version": 1}).status_code == 200
    assert client.get(url).json()["current_for_product"] is False
    assert client.put(url, json=label_payload(product, expected_revision=2)).status_code == 409
    assert client.put(url, json=label_payload(product, expected_revision=2, expected_mapping_version=2)).status_code == 200
    assert evaluate(client, "garlic")["decision"] == "eligible"


def test_composite_stock_cannot_hide_a_diet_conflict(client, catalog):
    declare(client, preferences=dict(diet_patterns=["no_pork"]))
    product = client.post("/api/v1/products/", json=dict(name="Rice and pork mix", unit="pack")).json()
    mapping = dict(mode="COMPOSITE", components=[dict(ingredient_id=catalog[name].id) for name in ("rice", "pork")],
        verified=True, unknown_composition=False, method="Package composition review", package_factors=[dict(
            ingredient_id=catalog["rice"].id, inventory_unit="pack", ingredient_amount=100,
            ingredient_unit="g", source_reference="Package quantity")])
    assert client.put(f"/api/v1/ingredients/products/{product['id']}/mapping", json=mapping).status_code == 200
    assert client.post("/api/v1/batches/", json=dict(product_id=product["id"], original_quantity=1)).status_code == 201
    assert client.put(f"/api/v1/food-safety/products/{product['id']}/label", json=label_payload(product)).status_code == 200
    result = evaluate(client, "rice")
    assert result["availability"]["overall_status"] == "full"
    assert result["decision"] == "blocked" and "dietary_restriction_conflict" in result["reasons"]


def test_exact_label_can_resolve_generic_possibilities_only_for_fully_covered_stock(client, catalog):
    declare(client, "wheat")
    product, _ = stock(client, catalog, name="soy sauce")
    url = f"/api/v1/food-safety/products/{product['id']}/label"
    assert client.put(url, json=label_payload(product)).status_code == 200
    requirement = dict(display_name="soy sauce", amount=1, unit="ml")
    assert evaluate(client, "soy sauce", requirements=[requirement])["decision"] == "eligible"
    requirement["amount"] = 11
    assert evaluate(client, "soy sauce", requirements=[requirement])["decision"] == "review_required"
    assert client.delete(url + "?expected_revision=1").status_code == 204
    requirement["amount"] = 1
    assert evaluate(client, "soy sauce", requirements=[requirement])["decision"] == "review_required"


def test_custom_label_declaration_cannot_be_cleared_by_unknown_custom_profile(client, catalog):
    declare(client, allergy_status="DECLARED", allergies=[dict(custom_text="Red additive X")])
    product, _ = stock(client, catalog)
    assert client.put(f"/api/v1/food-safety/products/{product['id']}/label",
        json=label_payload(product, custom_allergens=["Red additive X"])).status_code == 200
    result = evaluate(client, "garlic")
    assert result["decision"] == "blocked"
    assert "product_label_custom_allergen_conflict" in result["reasons"]


def test_vegan_preference_checks_label_allergens_outside_the_requested_ingredient(client, catalog):
    declare(client, preferences=dict(diet_patterns=["vegan"]))
    product, _ = stock(client, catalog, name="rice")
    assert client.put(f"/api/v1/food-safety/products/{product['id']}/label",
        json=label_payload(product, declared_allergens=["milk"])).status_code == 200
    assert evaluate(client, "rice")["decision"] == "blocked"


@pytest.mark.parametrize("patch", [dict(reviewed=False), dict(reviewed_by_user_id=999), dict(source_reference=" "),
    dict(declared_allergens=["milk", "milk"]), dict(declared_allergens=["milk"], possible_allergens=["milk"]),
    dict(declared_allergens=["invented"]), dict(household_id=999)])
def test_invalid_labels_are_rejected(client, db, catalog, patch):
    product, _ = stock(client, catalog)
    response = client.put(f"/api/v1/food-safety/products/{product['id']}/label", json=label_payload(product, **patch))
    assert response.status_code == 422
    assert db.scalar(select(func.count()).select_from(ProductAllergenLabel)) == 0


def test_foreign_product_and_unreviewed_mapping_cannot_receive_labels(client, db, catalog):
    foreign = Household(name="Private", slug="private-label")
    db.add(foreign)
    db.flush()
    product = Product(name="Foreign food", household_id=foreign.id)
    db.add(product)
    db.commit()
    url = f"/api/v1/food-safety/products/{product.id}/label"
    assert client.get(url).status_code == 404
    assert client.put(url, json=label_payload(product)).status_code == 404
    assert client.delete(url + "?expected_revision=1").status_code == 404
    own = client.post("/api/v1/products/", json=dict(name="Unreviewed", unit="g")).json()
    url = f"/api/v1/food-safety/products/{own['id']}/label"
    assert client.put(url, json=label_payload(own)).status_code == 409
    assert client.put(f"/api/v1/ingredients/products/{own['id']}/mapping", json=dict(mode="DIRECT",
        ingredient_id=catalog["garlic"].id, method="Unreviewed", unknown_composition=False)).status_code == 200
    assert client.put(url, json=label_payload(own)).status_code == 422


@pytest.mark.parametrize("existing", [False, True])
def test_concurrent_label_writes_accept_exactly_one_revision(client, db, engine, catalog, auth_user, auth_household, existing):
    product, _ = stock(client, catalog)
    if existing:
        assert client.put(f"/api/v1/food-safety/products/{product['id']}/label", json=label_payload(product)).status_code == 200
    household_id, user_id, product_id = auth_household.id, auth_user.id, product["id"]
    request = ProductLabelInput(**label_payload(product, expected_revision=1 if existing else None))
    db.rollback()
    barrier = Barrier(2)

    def write(_):
        with Session(engine) as independent:
            barrier.wait(timeout=10)
            try:
                return write_label(independent, household_id, product_id, user_id, request).revision
            except HTTPException as exc:
                independent.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as workers:
        result = list(workers.map(write, range(2)))
    assert sorted(result) == [2 if existing else 1, 409]
    assert db.scalar(select(func.count()).select_from(ProductAllergenLabel).where(ProductAllergenLabel.is_current.is_(True))) == 1
