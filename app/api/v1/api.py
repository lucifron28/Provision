from fastapi import APIRouter
from app.api.v1.endpoints import products, locations, batches, inventory, sessions, shopping, analytics

api_router = APIRouter()

api_router.include_router(products.router, prefix="/products", tags=["Products"])
api_router.include_router(locations.router, prefix="/locations", tags=["Storage Locations"])
api_router.include_router(batches.router, prefix="/batches", tags=["Inventory Batches"])
api_router.include_router(inventory.router, prefix="/inventory", tags=["Inventory Operations"])
api_router.include_router(sessions.router, prefix="/grocery-sessions", tags=["Grocery Sessions"])
api_router.include_router(shopping.router, prefix="/shopping-list", tags=["Shopping List"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Household Analytics"])
