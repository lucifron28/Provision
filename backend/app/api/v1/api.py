from fastapi import APIRouter, Depends
from app.api.v1.endpoints import (
    auth,
    products,
    locations,
    batches,
    inventory,
    sessions,
    shopping,
    analytics,
)
from app.api.v1.endpoints.auth import get_current_user

api_router = APIRouter()

# Public authentication endpoints
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])

# Protected household pantry endpoints
api_router.include_router(products.router, prefix="/products", tags=["Products"], dependencies=[Depends(get_current_user)])
api_router.include_router(locations.router, prefix="/locations", tags=["Storage Locations"], dependencies=[Depends(get_current_user)])
api_router.include_router(batches.router, prefix="/batches", tags=["Inventory Batches"], dependencies=[Depends(get_current_user)])
api_router.include_router(inventory.router, prefix="/inventory", tags=["Inventory Operations"], dependencies=[Depends(get_current_user)])
api_router.include_router(sessions.router, prefix="/grocery-sessions", tags=["Grocery Sessions"], dependencies=[Depends(get_current_user)])
api_router.include_router(shopping.router, prefix="/shopping-list", tags=["Shopping List"], dependencies=[Depends(get_current_user)])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Household Analytics"], dependencies=[Depends(get_current_user)])
