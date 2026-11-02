from fastapi import APIRouter, Depends
from app.api.v1.endpoints import (
    auth,
    households,
    privacy,
    products,
    locations,
    batches,
    inventory,
    sessions,
    shopping,
    analytics,
)
from app.api.v1.dependencies import get_current_household
from app.api.v1.endpoints import ingredients
from app.api.v1.endpoints import preferences
from app.api.v1.endpoints import food_safety
from app.api.v1.endpoints import recipes
from app.api.v1.endpoints import recipe_sources
from app.api.v1.endpoints import recipe_shopping
from app.api.v1.endpoints import meal_insights
from app.api.v1.endpoints import meal_plans, plan_shopping
from app.api.v1.endpoints import cooking, leftovers
from app.api.v1.endpoints import ai_recipes

api_router = APIRouter()
api_router.include_router(ingredients.router, prefix="/ingredients", tags=["Ingredients"])
api_router.include_router(preferences.router, prefix="/food-profiles", tags=["Food profiles"])
api_router.include_router(food_safety.router, prefix="/food-safety", tags=["Food safety"])
api_router.include_router(recipes.router, prefix="/recipes", tags=["Recipes"])
api_router.include_router(recipe_sources.router, prefix="/recipe-sources", tags=["Recipe sources"])
api_router.include_router(recipe_shopping.router, prefix="/recipe-shopping", tags=["Recipe shopping"])
api_router.include_router(meal_insights.router, prefix="/meal-insights", tags=["Meal insights"])
api_router.include_router(meal_plans.router, prefix="/meal-plans", tags=["Meal plans"])
api_router.include_router(plan_shopping.router, prefix="/plan-shopping", tags=["Plan shopping"])
api_router.include_router(cooking.router, prefix="/cooking", tags=["Cooking"])
api_router.include_router(leftovers.router, prefix="/leftovers", tags=["Leftovers"])
api_router.include_router(ai_recipes.router, prefix="/ai-recipes", tags=["AI recipes"])

# Public authentication endpoints
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(privacy.router, prefix="/privacy", tags=["Privacy"])
api_router.include_router(
    households.router,
    prefix="/households",
    tags=["Households"],
)

# Protected household pantry endpoints
api_router.include_router(products.router, prefix="/products", tags=["Products"], dependencies=[Depends(get_current_household)])
api_router.include_router(locations.router, prefix="/locations", tags=["Storage Locations"], dependencies=[Depends(get_current_household)])
api_router.include_router(batches.router, prefix="/batches", tags=["Inventory Batches"], dependencies=[Depends(get_current_household)])
api_router.include_router(inventory.router, prefix="/inventory", tags=["Inventory Operations"], dependencies=[Depends(get_current_household)])
api_router.include_router(sessions.router, prefix="/grocery-sessions", tags=["Grocery Sessions"], dependencies=[Depends(get_current_household)])
api_router.include_router(shopping.router, prefix="/shopping-list", tags=["Shopping List"], dependencies=[Depends(get_current_household)])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Household Analytics"], dependencies=[Depends(get_current_household)])
