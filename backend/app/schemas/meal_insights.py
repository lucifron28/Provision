from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, model_validator

from app.schemas.ingredients import StrictSchema
from app.schemas.recipe import RecipeEvaluationInput


class MealBudgetRequest(RecipeEvaluationInput):
    include_optional: bool = False


class MealBudgetLine(StrictSchema):
    ingredient_id: int | None
    ingredient_name: str
    amount: Decimal | None
    unit: str | None
    estimated_cost_php: Decimal | None = None
    price_batch_id: int | None = None
    price_product_id: int | None = None
    historical_unit_price_php: Decimal | None = None
    price_inventory_unit: str | None = None
    purchased_at: datetime | None = None
    store_name: str | None = None
    missing_reason: str | None = None


class MealBudgetRead(StrictSchema):
    recipe_id: int
    recipe_revision: int
    currency: Literal["PHP"] = "PHP"
    price_basis: Literal["historical_purchase_prices"] = "historical_purchase_prices"
    cost_basis: Literal["ingredient_usage_not_package_purchase"] = "ingredient_usage_not_package_purchase"
    complete: bool
    known_cost_subtotal_php: Decimal
    estimated_total_php: Decimal | None
    budget_goal_php: Decimal | None
    estimated_within_budget: bool | None
    lines: list[MealBudgetLine]
    notice: str = "Recorded prices are treated as PHP. Estimates are not current store quotes or allergy eligibility."


class WastePeriodRequest(StrictSchema):
    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def bounded_period(self):
        if self.end <= self.start or self.end - self.start > timedelta(days=366):
            raise ValueError("Use a positive reporting interval of at most 366 days")
        return self


class WasteUnitTotal(StrictSchema):
    unit: str | None
    quantity: Decimal


class WasteEventRead(StrictSchema):
    event_id: int
    batch_id: int
    product_id: int
    quantity: Decimal
    unit: str | None
    occurred_at: datetime
    type: Literal["DISCARDED", "EXPIRED"]
    recorded_unit_price_php: Decimal | None
    estimated_loss_php: Decimal | None
    cost_unknown_reason: str | None = None


class WastePeriodRead(StrictSchema):
    start: datetime
    end: datetime
    currency: Literal["PHP"] = "PHP"
    event_count: int
    priced_event_count: int
    unpriced_event_count: int
    known_loss_subtotal_php: Decimal
    estimated_total_loss_php: Decimal | None
    quantities_by_unit: list[WasteUnitTotal]
    events: list[WasteEventRead]
    methodology: str = "Explicit DISCARDED and EXPIRED ledger events in [start, end). Quantities are grouped by unit. No inferred savings or automatic waste."
