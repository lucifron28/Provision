from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MAX_AMOUNT = Decimal("99999999.999999")


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IngredientAliasRead(StrictSchema):
    alias: str
    language: str
    region: Optional[str] = None


class IngredientRead(StrictSchema):
    id: int
    canonical_name: str
    filipino_name: Optional[str] = None
    family: Optional[str] = None
    default_unit: Optional[str] = None
    aliases: list[IngredientAliasRead]
    is_active: bool


class IngredientLookupCandidate(IngredientRead):
    matched_alias: Optional[str] = None


class IngredientLookupRead(StrictSchema):
    query: Optional[str] = None
    ambiguous: bool = False
    results: list[IngredientLookupCandidate]


class MappingMode(str, Enum):
    DIRECT = "DIRECT"
    COMPOSITE = "COMPOSITE"
    UNKNOWN = "UNKNOWN"


class MappingVerificationStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    UNKNOWN = "UNKNOWN"


class IngredientComponentInput(StrictSchema):
    ingredient_id: int = Field(gt=0)


class PackageFactorInput(StrictSchema):
    ingredient_id: int = Field(gt=0)
    inventory_unit: str = Field(min_length=1, max_length=50)
    ingredient_amount: Decimal = Field(gt=0, le=MAX_AMOUNT, max_digits=14, decimal_places=6)
    ingredient_unit: str = Field(min_length=1, max_length=24)
    source_reference: str = Field(min_length=1, max_length=2000)

    @field_validator("ingredient_amount")
    @classmethod
    def finite_factor(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Package factor must be finite")
        return value

    @field_validator("inventory_unit", "ingredient_unit")
    @classmethod
    def trim_units(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Unit cannot be blank")
        return value

    @field_validator("source_reference")
    @classmethod
    def trim_source_reference(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Package factor requires a source reference")
        return value


class ProductIngredientMappingUpsert(StrictSchema):
    expected_version: Optional[int] = Field(default=None, ge=1)
    mode: MappingMode
    ingredient_id: Optional[int] = Field(default=None, gt=0)
    components: list[IngredientComponentInput] = Field(default_factory=list, max_length=100)
    verified: bool = False
    method: str = Field(min_length=1, max_length=80)
    confidence: Optional[Decimal] = Field(default=None, ge=0, le=1, max_digits=5, decimal_places=4)
    unknown_composition: bool = True
    package_factors: list[PackageFactorInput] = Field(default_factory=list, max_length=100)

    @field_validator("confidence")
    @classmethod
    def finite_confidence(cls, value: Optional[Decimal]) -> Optional[Decimal]:
        if value is not None and not value.is_finite():
            raise ValueError("Confidence must be finite")
        return value

    @field_validator("method")
    @classmethod
    def trim_method(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Mapping method cannot be blank")
        return value

    @model_validator(mode="after")
    def validate_mapping_shape(self) -> "ProductIngredientMappingUpsert":
        component_ids = [item.ingredient_id for item in self.components]
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("Composite mapping cannot repeat an ingredient")

        if self.mode is MappingMode.DIRECT:
            if self.ingredient_id is None or self.components:
                raise ValueError("Direct mapping requires one ingredient and no components")
            allowed_factor_ids = {self.ingredient_id}
        elif self.mode is MappingMode.COMPOSITE:
            if self.ingredient_id is not None or not self.components:
                raise ValueError("Composite mapping requires components and no direct ingredient")
            allowed_factor_ids = set(component_ids)
        else:
            if self.ingredient_id is not None or self.components or self.verified:
                raise ValueError("Unknown mapping cannot declare ingredients or be verified")
            if self.package_factors:
                raise ValueError("Unknown mapping cannot declare package factors")
            if not self.unknown_composition:
                raise ValueError("Unknown mapping must keep composition unknown")
            allowed_factor_ids = set()

        factor_ids = [factor.ingredient_id for factor in self.package_factors]
        if len(factor_ids) != len(set(factor_ids)):
            raise ValueError("A mapping cannot repeat a package factor")
        if not set(factor_ids).issubset(allowed_factor_ids):
            raise ValueError("Package factors must belong to the mapped ingredient or components")
        if self.package_factors and not self.verified:
            raise ValueError("Package factors require an explicitly verified mapping")
        if self.verified and self.mode is MappingMode.UNKNOWN:
            raise ValueError("Unknown mapping cannot be verified")
        return self


class PackageFactorRead(StrictSchema):
    ingredient_id: int
    inventory_unit: str
    ingredient_amount: Decimal
    ingredient_unit: str
    source_reference: str
    verified_by_user_id: Optional[int]
    verified_at: datetime


class ProductIngredientMappingRead(StrictSchema):
    id: int
    product_id: int
    version: int
    is_current: bool
    mode: MappingMode
    ingredient_id: Optional[int]
    verification_status: MappingVerificationStatus
    method: str
    verified_by_user_id: Optional[int]
    verified_at: Optional[datetime]
    confidence: Optional[Decimal]
    unknown_composition: bool
    component_ingredient_ids: list[int]
    package_factors: list[PackageFactorRead]
    created_at: datetime
    updated_at: datetime


class IngredientRequirementInput(StrictSchema):
    ingredient_id: Optional[int] = Field(default=None, gt=0)
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=180)
    amount: Decimal = Field(gt=0, le=MAX_AMOUNT, max_digits=14, decimal_places=6)
    unit: str = Field(min_length=1, max_length=50)
    required: bool = True

    @field_validator("amount")
    @classmethod
    def finite_amount(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Requirement amount must be finite")
        return value

    @field_validator("display_name", "unit")
    @classmethod
    def trim_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be blank")
        return value

    @model_validator(mode="after")
    def require_one_ingredient_reference(self) -> "IngredientRequirementInput":
        if (self.ingredient_id is None) == (self.display_name is None):
            raise ValueError("Provide exactly one of ingredient_id or display_name")
        return self


class RecipeAvailabilityRequest(StrictSchema):
    recipe_servings: Decimal = Field(gt=0, le=Decimal("10000"), max_digits=12, decimal_places=4)
    servings: Decimal = Field(gt=0, le=Decimal("10000"), max_digits=12, decimal_places=4)
    requirements: list[IngredientRequirementInput] = Field(min_length=1, max_length=200)

    @field_validator("recipe_servings", "servings")
    @classmethod
    def finite_servings(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Servings must be finite")
        return value


AvailabilityStatus = Literal["full", "partial", "missing", "unknown"]


class IngredientAvailabilityLine(StrictSchema):
    ingredient_id: Optional[int]
    canonical_name: Optional[str]
    display_names: list[str]
    required: bool
    required_amount: Optional[Decimal]
    available_amount: Optional[Decimal]
    shortfall: Optional[Decimal]
    unit: Optional[str]
    status: AvailabilityStatus
    covered_batch_ids: list[int]
    missing_expiry_batch_ids: list[int]
    unknown_reasons: list[str]


class RecipeAvailabilityRead(StrictSchema):
    recipe_servings: Decimal
    servings: Decimal
    overall_status: AvailabilityStatus
    requirements: list[IngredientAvailabilityLine]
