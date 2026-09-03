from fastapi import APIRouter
from app.api.v1.endpoints import products, locations

api_router = APIRouter()

api_router.include_router(products.router, prefix="/products", tags=["Products"])
api_router.include_router(locations.router, prefix="/locations", tags=["Storage Locations"])
