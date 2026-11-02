from datetime import datetime, timezone
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.allergens import IngredientDerivative
from app.models.household import HouseholdMembership
from app.models.ingredient import Ingredient
from app.models.user import User
from app.services.ingredient_matching import seed_ingredient_catalog_v1
from app.core.security import hash_password


@pytest.fixture
def catalog(db):
    seed_ingredient_catalog_v1(db)
    db.flush()
    path = Path(__file__).resolve().parents[1] / "alembic/versions/73ab14c6d982_add_allergen_graph.py"
    spec = importlib.util.spec_from_file_location("allergen_seed_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    migration._seed_catalog(db.connection())
    db.commit()
    return {item.normalized_name: item for item in db.scalars(select(Ingredient)).all()}


def declare(client, code=None, **kwargs):
    declaration = dict(allergen_code=code) if code else None
    payload = dict(allergy_status="DECLARED" if code else "NONE_DECLARED", allergies=[declaration] if code else [])
    payload.update(kwargs)
    response = client.put("/api/v1/food-profiles/me", json=payload)
    assert response.status_code == 200, response.text


def evaluate(client, name, **kwargs):
    payload = dict(recipe_servings=1, servings=1, requirements=[dict(display_name=name, amount=1, unit="g")])
    payload.update(kwargs)
    result = client.post("/api/v1/food-safety/evaluate", json=payload)
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "no-store"
    return result.json()


@pytest.mark.parametrize("name,code", [
    ("milk", "milk"), ("egg", "egg"), ("fish", "fish"), ("shrimp", "crustacean_shellfish"),
    ("almond", "tree_nuts"), ("peanut", "peanuts"), ("wheat", "wheat"), ("soybean", "soy"), ("sesame", "sesame"),
    ("whey", "milk"), ("casein", "milk"), ("cheese", "milk"), ("patis", "fish"),
    ("bagoong alamang", "crustacean_shellfish"), ("bagoong isda", "fish"),
    ("tokwa", "soy"), ("harina", "wheat"),
])
def test_direct_and_derived_allergens_block(client, catalog, name, code):
    declare(client, code)
    result = evaluate(client, name)
    assert result["decision"] == "blocked"
    assert "allergen_conflict" in result["reasons"]


def test_missing_allergy_data_never_becomes_none_declared(client, catalog):
    assert evaluate(client, "bawang")["decision"] == "review_required"
    declare(client)
    assert evaluate(client, "bawang")["decision"] == "eligible"


@pytest.mark.parametrize("name", ["bagoong", "unknown brand sauce", "toyo", "mantika"])
def test_ambiguous_and_composite_ingredients_need_review(client, catalog, name):
    declare(client, "wheat")
    result = evaluate(client, name)
    assert result["decision"] == "review_required"
    assert result["reasons"]


@pytest.mark.parametrize("diet,name,status", [
    ("vegan", "itlog", "blocked"), ("vegan", "whey", "blocked"),
    ("vegetarian", "patis", "blocked"), ("pescatarian", "pork", "blocked"),
    ("no_pork", "pork", "blocked"), ("dairy_free", "casein", "blocked"),
    ("gluten_free", "wheat flour", "blocked"), ("halal", "pork", "blocked"),
    ("halal", "chicken", "review_required"), ("vegan", "rice", "eligible"),
])
def test_diet_patterns_are_hard_gates(client, catalog, diet, name, status):
    declare(client, preferences=dict(diet_patterns=[diet]))
    assert evaluate(client, name)["decision"] == status


def test_selected_diner_union_and_private_details(client, db, auth_household, auth_user, catalog):
    declare(client)
    member = User(email="safety-member@example.test", hashed_password=hash_password("password123"), is_active=True)
    db.add(member)
    db.flush()
    db.add(HouseholdMembership(household_id=auth_household.id, user_id=member.id, role="MEMBER"))
    db.commit()
    from app.schemas.preferences import FoodProfileInput
    from app.services.preferences import write_profile
    write_profile(db, auth_household.id, member.id, member.id, FoodProfileInput(
        allergy_status="DECLARED", allergies=[dict(allergen_code="egg", notes="private-severe-note", severity="severe")]))
    result = evaluate(client, "egg")
    assert result["decision"] == "blocked"
    assert "private-severe-note" not in str(result) and "severe" not in str(result)
    assert evaluate(client, "egg", diner_user_ids=[auth_user.id])["decision"] == "eligible"
    denied = client.post("/api/v1/food-safety/evaluate", json=dict(recipe_servings=1, servings=1,
        requirements=[dict(display_name="egg", amount=1, unit="count")], diner_user_ids=[999999]))
    assert denied.status_code == 403


@pytest.mark.parametrize("text,decision", [("bawang", "blocked"), ("unrecognized additive", "review_required")])
def test_custom_allergen_resolution(client, catalog, text, decision):
    declare(client, allergy_status="DECLARED", allergies=[dict(custom_text=text)])
    assert evaluate(client, "garlic")["decision"] == decision


def test_every_substitution_rechecks_safety_and_preserves_required_demand(client, catalog):
    declare(client, "egg")
    assert evaluate(client, "egg")["decision"] == "blocked"
    replacement = dict(requirement_index=0, replacement=dict(display_name="garlic", amount=3, unit="g", required=False))
    result = evaluate(client, "egg", substitutions=[replacement])
    assert result["decision"] == "eligible"
    assert result["availability"]["requirements"][0]["required"] is True
    assert result["availability"]["requirements"][0]["required_amount"] == "3"
    assert result["availability"]["overall_status"] == "missing"
    replacement["replacement"]["display_name"] = "egg"
    assert evaluate(client, "garlic", substitutions=[replacement])["decision"] == "blocked"


def test_quantity_mapping_is_not_an_allergen_label(client, catalog):
    declare(client)
    product = client.post("/api/v1/products/", json=dict(name="Garlic product", unit="g")).json()
    mapped = client.put(f"/api/v1/ingredients/products/{product['id']}/mapping", json=dict(mode="DIRECT",
        ingredient_id=catalog["garlic"].id, verified=True, method="Explicit mapping", unknown_composition=False))
    assert mapped.status_code == 200
    assert client.post("/api/v1/batches/", json=dict(product_id=product["id"], original_quantity=10)).status_code == 201
    result = evaluate(client, "garlic")
    assert result["availability"]["overall_status"] == "full"
    assert result["decision"] == "review_required"
    assert "product_allergen_label_not_reviewed" in result["reasons"]


def test_cycle_and_unreviewed_derivatives_never_clear_conflicts(client, db, catalog):
    declare(client, "milk")
    edge = db.scalar(select(IngredientDerivative).where(IngredientDerivative.ingredient_id == catalog["whey"].id))
    edge.checked_at = None
    db.commit()
    assert evaluate(client, "whey")["decision"] == "review_required"
    now = datetime.now(timezone.utc)
    for child, parent in [("garlic", "onion"), ("onion", "garlic")]:
        db.add(IngredientDerivative(ingredient_id=catalog[child].id, parent_ingredient_id=catalog[parent].id,
            evidence_reference="Test cycle evidence", checked_at=now))
    db.commit()
    assert evaluate(client, "garlic")["decision"] == "review_required"


def test_request_cannot_override_safety(client, catalog):
    base = dict(recipe_servings=1, servings=1, requirements=[dict(display_name="egg", amount=1, unit="count")])
    for patch in [dict(ignore_allergens=True), dict(diner_user_ids=[]),
        dict(substitutions=[dict(requirement_index=9, replacement=base["requirements"][0])])]:
        assert client.post("/api/v1/food-safety/evaluate", json={**base, **patch}).status_code == 422


def test_safety_evaluation_requires_authentication(unauthed_client):
    assert unauthed_client.post("/api/v1/food-safety/evaluate", json=dict(recipe_servings=1, servings=1,
        requirements=[dict(display_name="egg", amount=1, unit="count")])).status_code == 401


def test_cross_contact_and_household_exclusions_remain_separate_from_dislikes(client, catalog):
    declare(client, "milk", allergies=[dict(allergen_code="milk", cross_contact_concern=True)])
    assert "cross_contact_requires_review" in evaluate(client, "garlic")["reasons"]
    shared = client.put("/api/v1/food-profiles/household", json=dict(allergy_status="NONE_DECLARED",
        preferences=dict(dislikes=["onion"], ingredient_exclusions=[catalog["garlic"].id])))
    assert shared.status_code == 200
    assert evaluate(client, "garlic")["decision"] == "blocked"
    assert evaluate(client, "onion")["decision"] == "review_required"
    assert "ingredient_exclusion_conflict" not in evaluate(client, "onion")["reasons"]
