from decimal import Decimal

import pytest

from app.services.units import UnitConversionError, convert_amount


@pytest.mark.parametrize("amount,source,target,expected", [
    ("0.125", "kg", "grams", "125"),
    ("250", "ml", "L", "0.25"),
    ("3", "pcs", "count", "3"),
    ("0", "g", "kg", "0"),
])
def test_exact_compatible_conversions(amount, source, target, expected):
    assert convert_amount(Decimal(amount), source, target) == Decimal(expected)


@pytest.mark.parametrize("amount,source,target", [
    ("1", "count", "g"), ("1", "ml", "g"),
    ("1", "pack", "count"), ("1", "cup", "g"),
    ("NaN", "g", "kg"), ("Infinity", "g", "kg"),
    ("-1", "g", "kg"),
])
def test_unknown_or_invalid_conversions_fail_closed(amount, source, target):
    with pytest.raises(UnitConversionError):
        convert_amount(Decimal(amount), source, target)
