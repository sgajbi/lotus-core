from decimal import Decimal

import pytest
from portfolio_common.decimal_amounts import decimal_or_none, required_decimal


class _StringCountedAmount:
    def __init__(self, value: str) -> None:
        self.value = value
        self.string_call_count = 0

    def __str__(self) -> str:
        self.string_call_count += 1
        return self.value


def test_decimal_or_none_preserves_missing_and_blank_values() -> None:
    assert decimal_or_none(None) is None
    assert decimal_or_none("") is None
    assert decimal_or_none("   ") is None


def test_decimal_or_none_preserves_decimal_instances_without_stringifying() -> None:
    value = Decimal("12.50")

    assert decimal_or_none(value) is value


def test_decimal_or_none_stringifies_non_decimal_values_once() -> None:
    value = _StringCountedAmount("7.25")

    assert decimal_or_none(value) == Decimal("7.25")
    assert value.string_call_count == 1


def test_decimal_or_none_returns_none_for_invalid_values() -> None:
    assert decimal_or_none("not-a-number") is None


def test_required_decimal_rejects_missing_required_values() -> None:
    with pytest.raises(ValueError, match="quantity is required"):
        required_decimal(" ", field_name="quantity")
