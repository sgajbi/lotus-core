from decimal import Decimal

import pytest

from src.services.query_service.app.services.integration_value_normalization import (
    as_decimal,
    control_code,
    string_list,
)


def test_as_decimal_preserves_decimal_instances() -> None:
    value = Decimal("10.2500")

    assert as_decimal(value) is value


def test_as_decimal_converts_stringable_values() -> None:
    assert as_decimal("0.1250") == Decimal("0.1250")
    assert as_decimal(5) == Decimal("5")


@pytest.mark.parametrize("value", [None, "", "   "])
def test_as_decimal_rejects_missing_required_values(value) -> None:
    with pytest.raises(ValueError, match="numeric value is required"):
        as_decimal(value)


def test_control_code_normalizes_and_defaults_blank_values() -> None:
    assert control_code(" accepted ") == "ACCEPTED"
    assert control_code(None, default="UNKNOWN") == "UNKNOWN"
    assert control_code("   ", default="UNKNOWN") == "UNKNOWN"


def test_string_list_keeps_nonblank_stringable_values() -> None:
    assert string_list(["DPM", "", "  ", 42]) == ["DPM", "42"]
    assert string_list(("DPM",)) == []
