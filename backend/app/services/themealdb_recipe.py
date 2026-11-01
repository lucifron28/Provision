"""Validate approved API recipe text without guessing ingredient quantities."""

import re

from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.themealdb import MealDBIngredientText, MealDBRecipeText
from app.services.source_urls import canonical_recipe_url
from app.services.themealdb_reviewed import ReviewedMeal


def _text(value, *, optional=False):
    if value is None and optional:
        return ""
    if not isinstance(value, str) or any(ord(c) < 32 and c not in "\n\r\t" or ord(c) == 127 for c in value):
        raise ValueError("Invalid recipe text")
    return value


def validate_reviewed_meal(meal: ReviewedMeal) -> MealDBRecipeText:
    """Keep source measures as text; this does not authorize stock or shopping use."""
    try:
        data = meal.data
        if not isinstance(data, dict):
            raise ValueError("Invalid meal")
        meal_id = _text(data.get("idMeal"))
        if not re.fullmatch(r"[0-9]{1,12}", meal_id):
            raise ValueError("Invalid meal ID")
        notices = {}
        for key, value in data.items():
            if not isinstance(key, str):
                raise ValueError("Invalid meal field")
            match = re.fullmatch(r"str(?:Ingredient|Measure)(\d+)", key)
            if match and not 1 <= int(match.group(1)) <= 20 and value not in (None, ""):
                raise ValueError("Unsupported ingredient slot")
            if any(term in key.casefold() for term in ("copyright", "license", "licence", "creativecommons")) and value not in (None, ""):
                notices[key] = _text(value)
        ingredients = []
        for index in range(1, 21):
            name = _text(data.get(f"strIngredient{index}"), optional=True).strip()
            measure = _text(data.get(f"strMeasure{index}"), optional=True).strip()
            if not name and measure:
                raise ValueError("Measure without ingredient")
            if name:
                ingredients.append(MealDBIngredientText(name=name, source_measure=measure))
        return MealDBRecipeText(
            meal_id=meal_id, provider_url=f"https://www.themealdb.com/meal/{meal_id}", title=_text(data.get("strMeal")),
            ingredients=ingredients, instructions=_text(data.get("strInstructions")),
            source_notices=notices,
            source_url=canonical_recipe_url(_text(data.get("strSource"))),
            api_source_id=meal.api_source_id, original_source_id=meal.original_source_id,
            api_source_revision=meal.api_source_revision, original_source_revision=meal.original_source_revision,
        )
    except (TypeError, ValueError, ValidationError):
        raise HTTPException(502, "INVALID_MEALDB_RECIPE") from None
