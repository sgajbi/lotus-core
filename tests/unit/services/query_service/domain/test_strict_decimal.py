from decimal import Decimal

from src.services.query_service.app.services.decimal_amounts import decimal_or_none, decimal_or_zero


class _StringCountedAmount:
    def __init__(self, value: str) -> None:
        self.value = value
        self.string_call_count = 0

    def __str__(self) -> str:
        self.string_call_count += 1
        return self.value


def test_decimal_or_zero_handles_null_and_blank_values() -> None:
    assert decimal_or_zero(None) == Decimal("0")
    assert decimal_or_zero("") == Decimal("0")
    assert decimal_or_zero("   ") == Decimal("0")


def test_decimal_or_zero_preserves_decimal_instances_without_stringifying() -> None:
    value = Decimal("12.50")

    assert decimal_or_zero(value) is value


def test_decimal_or_zero_stringifies_non_decimal_values_once() -> None:
    value = _StringCountedAmount("7.25")

    assert decimal_or_zero(value) == Decimal("7.25")
    assert value.string_call_count == 1


def test_decimal_or_none_preserves_null_and_blank_values() -> None:
    assert decimal_or_none(None) is None
    assert decimal_or_none("") is None
    assert decimal_or_none("   ") is None


def test_decimal_or_none_preserves_decimal_instances_without_stringifying() -> None:
    value = Decimal("18.75")

    assert decimal_or_none(value) is value


def test_decimal_or_none_stringifies_non_decimal_values_once() -> None:
    value = _StringCountedAmount("3.50")

    assert decimal_or_none(value) == Decimal("3.50")
    assert value.string_call_count == 1
