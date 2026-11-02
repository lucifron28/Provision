from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from app.schemas.ingredients import StrictSchema
from app.schemas.preferences import AllergenCode


class ProductLabelInput(StrictSchema):
    expected_revision: int | None = Field(default=None, ge=1)
    expected_mapping_version: int = Field(ge=1)
    expected_product_updated_at: AwareDatetime
    reviewed: Literal[True]
    declared_allergens: list[AllergenCode] = Field(default_factory=list, max_length=9)
    possible_allergens: list[AllergenCode] = Field(default_factory=list, max_length=9)
    custom_allergens: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=180)]] = Field(default_factory=list, max_length=100)
    composition_known: bool = False
    source_reference: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_label(self):
        self.source_reference = self.source_reference.strip()
        if not self.source_reference:
            raise ValueError("A label review requires a source reference")
        for field in ("declared_allergens", "possible_allergens", "custom_allergens"):
            values = [item.casefold() for item in getattr(self, field)]
            if len(values) != len(set(values)):
                raise ValueError("Label declarations cannot be duplicated")
        if set(self.declared_allergens) & set(self.possible_allergens):
            raise ValueError("An allergen cannot be both declared and possible")
        return self


class ProductLabelRead(StrictSchema):
    product_id: int
    mapping_version: int
    revision: int
    declared_allergens: list[AllergenCode]
    possible_allergens: list[AllergenCode]
    custom_allergens: list[str]
    composition_known: bool
    source_reference: str
    reviewed_by_user_id: int | None
    reviewed_at: datetime
    current_for_product: bool
    revoked: bool
    revoked_at: datetime | None
    revoked_by_user_id: int | None
