"""Exact conversions within known dimensions, without inferred package sizes."""

from decimal import Decimal, InvalidOperation


class UnitConversionError(ValueError):
    pass


_ALIASES = {
    "g": "g", "gram": "g", "grams": "g",
    "kg": "kg", "kilogram": "kg", "kilograms": "kg",
    "ml": "ml", "milliliter": "ml", "milliliters": "ml",
    "l": "l", "liter": "l", "liters": "l",
    "count": "count", "pc": "count", "pcs": "count",
    "piece": "count", "pieces": "count", "item": "count", "items": "count",
}
_SCALES = {
    "g": ("mass", Decimal("1")),
    "kg": ("mass", Decimal("1000")),
    "ml": ("volume", Decimal("1")),
    "l": ("volume", Decimal("1000")),
    "count": ("count", Decimal("1")),
}


def normalize_unit(unit: str) -> str:
    normalized = _ALIASES.get(unit.strip().casefold())
    if normalized is None:
        raise UnitConversionError(f"Unit requires an explicit conversion reference: {unit}")
    return normalized


def convert_amount(amount: Decimal, source_unit: str, target_unit: str) -> Decimal:
    """Convert a finite nonnegative quantity only between compatible SI units."""
    try:
        quantity = Decimal(str(amount))
    except (InvalidOperation, ValueError) as exc:
        raise UnitConversionError("Quantity must be a finite nonnegative decimal") from exc
    if not quantity.is_finite() or quantity < 0:
        raise UnitConversionError("Quantity must be a finite nonnegative decimal")
    source = normalize_unit(source_unit)
    target = normalize_unit(target_unit)
    source_dimension, source_scale = _SCALES[source]
    target_dimension, target_scale = _SCALES[target]
    if source_dimension != target_dimension:
        raise UnitConversionError("Conversion between measurement dimensions requires verified evidence")
    return quantity * source_scale / target_scale
