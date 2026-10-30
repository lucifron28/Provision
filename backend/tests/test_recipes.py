from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi import HTTPException
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.household import Household, HouseholdMembership
from app.models.recipe import Recipe, RecipeIngredient, RecipeRevision, SavedRecipe
from app.models.user import User
from app.core.security import create_access_token, hash_password
from app.schemas.recipe import RecipeWrite
from app.services.recipes import write_recipe
from test_food_safety import catalog, declare


def recipe_payload(**kwargs):
    payload = dict(title="Garlic rice", cuisine="Filipino", ph_regions=["region_unknown"],
        course_categories=["breakfast"], dish_types=["rice"], servings=2, prep_minutes=5, cook_minutes=10,
        instructions=["Prepare the measured ingredients.", "Cook the rice with garlic until done."],
        ingredients=[dict(display_name="bigas", amount=100, unit="g"), dict(display_name="bawang", amount=5, unit="g")])
    payload.update(kwargs)
    return payload


def create(client, **kwargs):
    response = client.post("/api/v1/recipes/", json=recipe_payload(**kwargs))
    assert response.status_code == 201, response.text
    return response.json()


def test_recipe_revisions_archive_and_category_roundtrip(client, db, catalog):
    recipe = create(client)
    assert recipe["provenance"] == "USER_ENTERED" and recipe["revision"] == 1
    assert recipe["ingredients"][0]["ingredient_id"] == catalog["rice"].id
    url = f"/api/v1/recipes/{recipe['id']}"
    assert client.get(url).headers["cache-control"] == "no-store"
    updated = client.put(url, json=recipe_payload(expected_revision=1, title="Revised rice", ph_regions=["Tagalog"]))
    assert updated.status_code == 200 and updated.json()["revision"] == 2
    assert client.put(url, json=recipe_payload(expected_revision=1)).status_code == 409
    original = client.get(url + "/versions/1")
    assert original.json()["title"] == "Garlic rice" and original.json()["ph_regions"] == ["region_unknown"]
    assert db.scalar(select(func.count()).select_from(RecipeRevision)) == 2
    assert db.scalar(select(func.count()).select_from(RecipeIngredient)) == 2
    assert client.delete(url + "?expected_revision=1").status_code == 409
    assert client.delete(url + "?expected_revision=2").status_code == 204
    assert client.get("/api/v1/recipes/").json() == []
    assert client.get(url).json()["is_active"] is False
    assert client.get(url + "/versions/1").json()["title"] == "Garlic rice"


@pytest.mark.parametrize("patch", [dict(servings="NaN"), dict(title=" "), dict(instructions=[]),
    dict(instructions=[" "]), dict(ph_regions=["Bicolano", "region_unknown"]), dict(ph_regions=["invented"]),
    dict(course_categories=["breakfast", "breakfast"]), dict(household_id=99), dict(provenance="VERIFIED_PUBLISHER"),
    dict(source_url="https://example.test/copied-recipe"), dict(difficulty="invented"),
    dict(ingredients=[dict(display_name="egg", amount=-1, unit="count")]),
    dict(ingredients=[dict(ingredient_id=999999, amount=1, unit="g")]),
    dict(ingredients=[dict(display_name="garlic", amount=1, unit="g", substitution_options=[dict(ingredient_id=999999, amount=1, unit="g")])]),
])
def test_invalid_recipe_requests_do_not_write(client, db, patch):
    response = client.post("/api/v1/recipes/", json=recipe_payload(**patch))
    assert response.status_code == 422, response.text
    assert db.scalar(select(func.count()).select_from(Recipe)) == 0


def test_recipe_evaluation_loads_stored_requirements_and_rechecks_substitution(client, catalog):
    declare(client, "egg")
    recipe = create(client, title="Egg meal", ingredients=[dict(display_name="egg", amount=2, unit="count")])
    url = f"/api/v1/recipes/{recipe['id']}/evaluate"
    payload = dict(expected_recipe_revision=1, servings=1)
    result = client.post(url, json=payload)
    assert result.status_code == 200, result.text
    assert result.json()["result"]["decision"] == "blocked"
    assert client.post(url, json={**payload, "requirements": []}).status_code == 422
    assert client.post(url, json={**payload, "expected_recipe_revision": 2}).status_code == 409
    substitution = [dict(requirement_index=0, replacement=dict(display_name="garlic", amount=3, unit="g"))]
    result = client.post(url, json={**payload, "substitutions": substitution})
    assert result.status_code == 200 and result.json()["result"]["decision"] == "eligible"
    substitution[0]["requirement_index"] = 3
    assert client.post(url, json={**payload, "substitutions": substitution}).status_code == 422


def test_saved_recipes_pin_version_and_unsave_erases_private_notes(client, db, catalog):
    recipe = create(client)
    url = f"/api/v1/recipes/{recipe['id']}"
    saved = client.put(url + "/saved", json=dict(expected_recipe_revision=1, favorite=True, servings="3.5", notes="Private cooking note"))
    assert saved.status_code == 200 and saved.json()["revision"] == 1
    assert client.put(url, json=recipe_payload(expected_revision=1, title="Changed meal")).status_code == 200
    assert client.get(url + "/saved").json()["recipe_revision"] == 1
    assert client.put(url + "/saved", json=dict(expected_revision=1, expected_recipe_revision=1)).status_code == 409
    assert client.delete(url + "/saved?expected_revision=1").status_code == 204
    assert client.get("/api/v1/recipes/saved").json() == []
    tombstone = client.get(url + "/saved").json()
    assert tombstone["notes"] is None and tombstone["revision"] == 2
    assert client.put(url + "/saved", json=dict(expected_recipe_revision=2)).status_code == 409
    assert client.put(url + "/saved", json=dict(expected_revision=2, expected_recipe_revision=2)).status_code == 200
    assert db.scalar(select(func.count()).select_from(SavedRecipe)) == 1


def test_foreign_recipe_ids_are_rejected_across_routes(client, db):
    foreign = Household(name="Foreign", slug="foreign-recipe")
    db.add(foreign)
    db.flush()
    recipe = Recipe(household_id=foreign.id, title="Foreign meal", cuisine="Filipino", content={}, revision=1, is_active=True)
    db.add(recipe)
    db.commit()
    url = f"/api/v1/recipes/{recipe.id}"
    assert client.get("/api/v1/recipes/").json() == []
    assert client.get(url).status_code == 404
    assert client.get(url + "/versions/1").status_code == 404
    assert client.put(url, json=recipe_payload(expected_revision=1)).status_code == 404
    assert client.post(url + "/evaluate", json=dict(expected_recipe_revision=1, servings=2)).status_code == 404
    assert client.put(url + "/saved", json=dict(expected_recipe_revision=1)).status_code == 404
    assert client.delete(url + "?expected_revision=1").status_code == 404


def test_saved_recipe_notes_are_private_exportable_and_deleted_with_account(unauthed_client, db, auth_user, auth_household):
    member = User(email="recipe-member@example.test", hashed_password=hash_password("member-secret"), is_active=True)
    db.add(member)
    db.flush()
    db.add(HouseholdMembership(household_id=auth_household.id, user_id=member.id, role="MEMBER", is_default=True))
    db.commit()
    owner_headers = {"Authorization": "Bearer " + create_access_token(subject=auth_user.email, user_id=auth_user.id)}
    member_headers = {"Authorization": "Bearer " + create_access_token(subject=member.email, user_id=member.id)}
    response = unauthed_client.post("/api/v1/recipes/", headers=owner_headers, json=recipe_payload())
    assert response.status_code == 201
    recipe_id = response.json()["id"]
    for headers, note in [(owner_headers, "owner-private-note"), (member_headers, "member-private-note")]:
        assert unauthed_client.put(f"/api/v1/recipes/{recipe_id}/saved", headers=headers,
            json=dict(expected_recipe_revision=1, notes=note)).status_code == 200
    response = unauthed_client.get("/api/v1/recipes/saved", headers=member_headers)
    assert "member-private-note" in response.text and "owner-private-note" not in response.text
    exported = unauthed_client.get("/api/v1/privacy/export", headers=member_headers)
    assert exported.status_code == 200
    assert "member-private-note" in exported.text and "owner-private-note" not in exported.text
    assert len(exported.json()["recipes"]) == 1
    deleted = unauthed_client.post("/api/v1/privacy/account-deletion", headers=member_headers,
        json=dict(confirmation="DELETE MY ACCOUNT", password="member-secret"))
    assert deleted.status_code == 204
    assert db.scalar(select(func.count()).select_from(SavedRecipe).where(SavedRecipe.member_user_id == member.id)) == 0


def test_recipe_api_requires_authentication(unauthed_client):
    assert unauthed_client.get("/api/v1/recipes/").status_code == 401


def test_concurrent_recipe_updates_accept_only_one_version(client, db, engine, catalog, auth_household, auth_user):
    recipe = create(client)
    household_id, user_id = auth_household.id, auth_user.id
    request = RecipeWrite(**recipe_payload(expected_revision=1))
    db.rollback()
    barrier = Barrier(2)

    def write(_):
        with Session(engine) as independent:
            barrier.wait(timeout=10)
            try:
                return write_recipe(independent, household_id, user_id, request, recipe["id"]).revision
            except HTTPException as exc:
                independent.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(write, range(2)))
    assert sorted(results) == [2, 409]
    assert db.scalar(select(func.count()).select_from(RecipeRevision)) == 2
