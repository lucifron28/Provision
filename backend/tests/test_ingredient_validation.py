from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.ingredients import (
    IngredientRequirementInput,
    PackageFactorInput,
    ProductIngredientMappingUpsert,
    RecipeAvailabilityRequest,
)


def _requirement(**overrides: object) -> dict[str, object]:
    return {
        "ingredient_id": 17,
        "amount": Decimal("1.25"),
        "unit": "g",
        **overrides,
    }


def _factor(**overrides: object) -> dict[str, object]:
    return {
        "ingredient_id": 17,
        "inventory_unit": "pack",
        "ingredient_amount": Decimal("250"),
        "ingredient_unit": "g",
        "source_reference": "Package label states 250 g per pack",
        **overrides,
    }


def _mapping(**overrides: object) -> dict[str, object]:
    return {
        "mode": "DIRECT",
        "ingredient_id": 17,
        "method": "package label",
        **overrides,
    }


def _availability(**overrides: object) -> dict[str, object]:
    return {
        "recipe_servings": Decimal("2"),
        "servings": Decimal("4"),
        "requirements": [_requirement()],
        **overrides,
    }


@pytest.mark.parametrize(
    ("schema", "payload", "quantity_field"),
    [
        pytest.param(
            IngredientRequirementInput,
            _requirement(),
            "amount",
            id="ingredient-requirement",
        ),
        pytest.param(
            PackageFactorInput,
            _factor(),
            "ingredient_amount",
            id="package-factor",
        ),
    ],
)
@pytest.mark.parametrize(
    "quantity",
    [
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        Decimal("-0.01"),
        Decimal("0"),
        Decimal("1000000000.000001"),
        Decimal("1.1234567"),
    ],
    ids=["nan", "positive-infinity", "negative-infinity", "negative", "zero", "overflow", "precision"],
)
def test_ingredient_quantities_reject_nonfinite_nonpositive_and_out_of_range_values(
    schema: type,
    payload: dict[str, object],
    quantity_field: str,
    quantity: Decimal,
) -> None:
    invalid_payload = {**payload, quantity_field: quantity}

    with pytest.raises(ValidationError):
        schema.model_validate(invalid_payload)


@pytest.mark.parametrize("field", ["recipe_servings", "servings"])
@pytest.mark.parametrize(
    "quantity",
    [
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-1"),
        Decimal("0"),
        Decimal("10000.0001"),
        Decimal("1.12345"),
    ],
    ids=["nan", "infinity", "negative", "zero", "above-maximum", "precision"],
)
def test_recipe_servings_reject_invalid_bounds_and_precision(
    field: str, quantity: Decimal
) -> None:
    with pytest.raises(ValidationError):
        RecipeAvailabilityRequest.model_validate(_availability(**{field: quantity}))


@pytest.mark.parametrize(
    "overrides",
    [
        {"verified": True},
        {"components": [{"ingredient_id": 23}]},
        {"package_factors": [_factor(ingredient_id=23)]},
        {"unknown_composition": False},
    ],
    ids=["verified", "components", "factors", "known-composition"],
)
def test_unknown_mapping_cannot_claim_verification_or_ingredient_facts(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ProductIngredientMappingUpsert.model_validate(
            _mapping(mode="UNKNOWN", ingredient_id=None, **overrides)
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"ingredient_id": None},
        {"components": [{"ingredient_id": 23}]},
        {"ingredient_id": None, "components": [{"ingredient_id": 23}]},
    ],
    ids=["missing-target", "direct-with-child", "children-without-target"],
)
def test_direct_mapping_requires_one_target_and_no_components(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ProductIngredientMappingUpsert.model_validate(_mapping(**overrides))


def test_composite_mapping_accepts_distinct_components() -> None:
    mapping = ProductIngredientMappingUpsert.model_validate(
        _mapping(
            mode="COMPOSITE",
            ingredient_id=None,
            components=[{"ingredient_id": 23}, {"ingredient_id": 29}],
        )
    )

    assert [component.ingredient_id for component in mapping.components] == [23, 29]


def test_composite_mapping_rejects_duplicate_components() -> None:
    with pytest.raises(ValidationError):
        ProductIngredientMappingUpsert.model_validate(
            _mapping(
                mode="COMPOSITE",
                ingredient_id=None,
                components=[{"ingredient_id": 23}, {"ingredient_id": 23}],
            )
        )


@pytest.mark.parametrize(
    "mapping_values",
    [
        pytest.param(
            {"mode": "DIRECT", "ingredient_id": 17},
            id="direct-target-mismatch",
        ),
        pytest.param(
            {"mode": "COMPOSITE", "ingredient_id": None, "components": [{"ingredient_id": 23}]},
            id="composite-component-mismatch",
        ),
    ],
)
def test_package_factor_ingredient_must_belong_to_mapping(
    mapping_values: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ProductIngredientMappingUpsert.model_validate(
            _mapping(
                **mapping_values,
                verified=True,
                package_factors=[_factor(ingredient_id=29)],
            )
        )


def test_package_factors_require_a_verified_mapping() -> None:
    with pytest.raises(ValidationError):
        ProductIngredientMappingUpsert.model_validate(
            _mapping(package_factors=[_factor()])
        )


def test_verified_direct_mapping_accepts_factor_for_its_target() -> None:
    mapping = ProductIngredientMappingUpsert.model_validate(
        _mapping(verified=True, package_factors=[_factor()])
    )

    assert mapping.verified is True
    assert mapping.package_factors[0].ingredient_id == mapping.ingredient_id


def test_verified_composite_mapping_accepts_factor_for_a_component() -> None:
    mapping = ProductIngredientMappingUpsert.model_validate(
        _mapping(
            mode="COMPOSITE",
            ingredient_id=None,
            components=[{"ingredient_id": 23}, {"ingredient_id": 29}],
            verified=True,
            package_factors=[_factor(ingredient_id=29)],
        )
    )

    assert mapping.package_factors[0].ingredient_id == 29


@pytest.mark.parametrize(
    "confidence",
    [
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-0.0001"),
        Decimal("1.0001"),
        Decimal("0.12345"),
    ],
    ids=["nan", "infinity", "below-zero", "above-one", "precision"],
)
def test_confidence_rejects_nonfinite_out_of_bounds_and_overprecise_values(
    confidence: Decimal,
) -> None:
    with pytest.raises(ValidationError):
        ProductIngredientMappingUpsert.model_validate(_mapping(confidence=confidence))


@pytest.mark.parametrize(
    "field",
    ["unexpected", "household_id", "verified_by_user_id", "verified_at"],
)
def test_mapping_rejects_extra_and_server_owned_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        ProductIngredientMappingUpsert.model_validate(_mapping(**{field: 99}))


def test_package_factor_rejects_forged_verifier_field() -> None:
    with pytest.raises(ValidationError):
        PackageFactorInput.model_validate(_factor(verified_by_user_id=99))


@pytest.mark.parametrize(
    "payload",
    [
        {"amount": Decimal("1"), "unit": "g"},
        {"ingredient_id": 17, "display_name": "garlic", "amount": Decimal("1"), "unit": "g"},
    ],
    ids=["neither-reference", "both-references"],
)
def test_requirement_requires_exactly_one_ingredient_reference(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        IngredientRequirementInput.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"ingredient_id": 17, "amount": Decimal("1"), "unit": "g"},
        {"display_name": "garlic", "amount": Decimal("1"), "unit": "g"},
    ],
    ids=["by-id", "by-display-name"],
)
def test_requirement_accepts_one_ingredient_reference(
    payload: dict[str, object],
) -> None:
    requirement = IngredientRequirementInput.model_validate(payload)

    assert (requirement.ingredient_id is None) != (requirement.display_name is None)


@pytest.mark.parametrize(
    ("schema", "payload", "field"),
    [
        pytest.param(ProductIngredientMappingUpsert, _mapping(), "method", id="method"),
        pytest.param(IngredientRequirementInput, _requirement(), "unit", id="requirement-unit"),
        pytest.param(PackageFactorInput, _factor(), "inventory_unit", id="inventory-unit"),
        pytest.param(PackageFactorInput, _factor(), "ingredient_unit", id="ingredient-unit"),
        pytest.param(PackageFactorInput, _factor(), "source_reference", id="source-reference"),
    ],
)
@pytest.mark.parametrize("blank", ["", " \t "], ids=["empty", "whitespace"])
def test_required_mapping_text_rejects_blank_values(
    schema: type, payload: dict[str, object], field: str, blank: str
) -> None:
    with pytest.raises(ValidationError):
        schema.model_validate({**payload, field: blank})
