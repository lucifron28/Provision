import json
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

from app.models.recipe import Recipe, RecipeRevision
from app.models.recipe_source import RecipeSource, RecipeSourceReference
from test_food_safety import catalog, declare


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "filipino_recipes.json"


def _dataset():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _recipe_payload(dataset, item):
    return {
        **dataset["defaults"],
        **{key: value for key, value in item.items() if key != "ingredients"},
        "ingredients": item["ingredients"],
    }


def test_fixture_covers_requested_filipino_recipe_families():
    dataset = _dataset()
    recipes = dataset["recipes"]
    titles = {item["title"].casefold() for item in recipes}

    assert len(recipes) >= 30
    assert dataset["defaults"]["ph_regions"] == ["region_unknown"]
    assert all(
        item.get("ph_regions", dataset["defaults"]["ph_regions"])
        == ["region_unknown"]
        for item in recipes
    )
    assert all("Synthetic fixture direction:" in item["instructions"][0] for item in recipes)
    assert all("source_url" not in item and "publisher" not in item for item in recipes)
    for family in (
        "adobo", "sinigang", "tinola", "pancit", "ginisang monggo",
        "tortang talong", "arroz caldo", "lumpia", "champorado",
    ):
        assert any(family in title for title in titles)

    assert {category for item in recipes for category in item["course_categories"]} >= {
        "breakfast", "lunch", "dinner", "merienda", "dessert", "baon", "fiesta"
    }
    assert any(
        line.get("required") is False
        for item in recipes
        for line in item["ingredients"]
    )
    assert any(line["display_name"] == "patis" for item in recipes for line in item["ingredients"])
    assert any(line["display_name"] == "bagoong" for item in recipes for line in item["ingredients"])


def test_filipino_recipes_persist_match_scale_and_apply_safety(client, db, catalog):
    dataset = _dataset()
    created = {}

    for item in dataset["recipes"]:
        response = client.post("/api/v1/recipes/", json=_recipe_payload(dataset, item))
        assert response.status_code == 201, f"{item['title']}: {response.text}"
        saved = response.json()
        assert saved["provenance"] == "USER_ENTERED"
        assert saved["ph_regions"] == ["region_unknown"]
        created[item["title"]] = saved

    assert len(created) == len(dataset["recipes"]) >= 30
    assert db.scalar(select(func.count()).select_from(Recipe)) == len(created)
    assert db.scalar(select(func.count()).select_from(RecipeRevision)) == len(created)
    assert db.scalar(select(func.count()).select_from(RecipeSource)) == 0
    assert db.scalar(select(func.count()).select_from(RecipeSourceReference)) == 0

    adobo = created["Adobo sa baboy"]
    matched = {line["display_name"]: line["ingredient_id"] for line in adobo["ingredients"]}
    assert matched["baboy"] == catalog["pork"].id
    assert matched["bawang"] == catalog["garlic"].id
    assert matched["toyo"] == catalog["soy sauce"].id

    declare(client, "fish")
    evaluate_url = f"/api/v1/recipes/{adobo['id']}/evaluate"
    base_request = {"expected_recipe_revision": 1, "servings": "8"}
    without_optional = client.post(evaluate_url, json={**base_request, "include_optional": False})
    assert without_optional.status_code == 200, without_optional.text
    omitted = without_optional.json()
    assert omitted["included_requirement_indexes"] == [0, 1, 2, 3, 4]
    quantities = {
        line["canonical_name"]: (Decimal(line["required_amount"]), line["unit"])
        for line in omitted["result"]["availability"]["requirements"]
    }
    assert quantities["pork"] == (Decimal("800"), "g")
    assert quantities["garlic"] == (Decimal("20"), "g")
    assert quantities["onion"] == (Decimal("100"), "g")
    assert quantities["soy sauce"] == (Decimal("120"), "ml")
    assert quantities["vinegar"] == (Decimal("120"), "ml")
    assert omitted["result"]["decision"] != "blocked"

    with_optional = client.post(evaluate_url, json={**base_request, "include_optional": True})
    assert with_optional.status_code == 200, with_optional.text
    included = with_optional.json()
    assert included["included_requirement_indexes"] == list(range(7))
    fish_sauce = next(
        line for line in included["result"]["availability"]["requirements"]
        if line["canonical_name"] == "fish sauce" and not line["required"]
    )
    assert Decimal(fish_sauce["required_amount"]) == Decimal("10")
    assert fish_sauce["unit"] == "ml"
    assert included["result"]["decision"] == "blocked"
    assert "allergen_conflict" in included["result"]["reasons"]

    recommendation = client.post("/api/v1/recipes/recommendations", json={
        "query": "Adobo sa baboy", "servings": "8", "mode": "all",
    })
    assert recommendation.status_code == 200, recommendation.text
    ranked = recommendation.json()
    assert ranked["provider_enabled"] is False
    assert ranked["items"] == []
    assert ranked["excluded_blocked"] == 1

    ambiguous = created["Ginisang monggo na may bagoong"]
    ambiguous_result = client.post(
        f"/api/v1/recipes/{ambiguous['id']}/evaluate",
        json={"expected_recipe_revision": 1, "servings": "4"},
    )
    assert ambiguous_result.status_code == 200, ambiguous_result.text
    ambiguous_line = next(
        line for line in ambiguous_result.json()["result"]["availability"]["requirements"]
        if "bagoong" in line["display_names"]
    )
    assert ambiguous_line["ingredient_id"] is None
    assert ambiguous_line["status"] == "unknown"
    assert "ambiguous_ingredient_name" in ambiguous_line["unknown_reasons"]

    lumpia = created["Lumpiang gulay"]
    lumpia_result = client.post(
        f"/api/v1/recipes/{lumpia['id']}/evaluate",
        json={"expected_recipe_revision": 1, "servings": "8"},
    )
    assert lumpia_result.status_code == 200, lumpia_result.text
    wrapper = next(
        line for line in lumpia_result.json()["result"]["availability"]["requirements"]
        if "lumpia wrapper" in line["display_names"]
    )
    assert wrapper["ingredient_id"] is None
    assert wrapper["status"] == "unknown"
