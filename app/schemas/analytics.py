from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class InventorySummaryItem(BaseModel):
    product_id: int
    product_name: str
    brand: Optional[str] = None
    category: Optional[str] = None
    total_remaining: float
    unit: Optional[str] = None
    active_batches_count: int
    locations: List[str] = []


class ExpiringSoonItem(BaseModel):
    batch_id: int
    product_id: int
    product_name: str
    brand: Optional[str] = None
    remaining_quantity: float
    unit: Optional[str] = None
    expiration_date: date
    days_until_expiration: int
    storage_location: Optional[str] = None


class LowStockItem(BaseModel):
    product_id: int
    product_name: str
    brand: Optional[str] = None
    current_stock: float
    unit: Optional[str] = None


class InventoryValuation(BaseModel):
    total_value: float
    total_active_batches: int
    total_active_products: int


class SpendingItem(BaseModel):
    session_id: Optional[int] = None
    store_name: Optional[str] = None
    purchase_date: datetime
    amount: float


class SpendingSummary(BaseModel):
    total_spent: float
    sessions_count: int
    recent_transactions: List[SpendingItem] = []


class WasteItem(BaseModel):
    event_id: int
    product_name: str
    event_type: str
    quantity: float
    unit: Optional[str] = None
    occurred_at: datetime
    estimated_cost_wasted: Optional[float] = None
    reason: Optional[str] = None


class WasteSummary(BaseModel):
    total_waste_events: int
    total_quantity_wasted: float
    total_financial_loss: float
    wasted_items: List[WasteItem] = []


class PriceHistoryPoint(BaseModel):
    batch_id: int
    purchased_at: datetime
    unit_price: float
    store_name: Optional[str] = None


class ProductPriceHistory(BaseModel):
    product_id: int
    product_name: str
    price_points: List[PriceHistoryPoint] = []
