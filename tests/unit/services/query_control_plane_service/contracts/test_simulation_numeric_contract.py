from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.services.query_control_plane_service.app.contracts.simulation import (
    SimulationChangeInput,
)


def _change(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "security_id": "SEC_AAPL_US",
        "transaction_type": "BUY",
        "quantity": "10.0000000000",
        "price": "210.5000000000",
        "amount": "2105.0000000000",
        "currency": "USD",
    }
    payload.update(overrides)
    return payload


def test_simulation_change_accepts_exact_storage_boundaries() -> None:
    change = SimulationChangeInput.model_validate(
        _change(
            quantity="-99999999.9999999999",
            price="99999999.9999999999",
            amount="99999999.9999999999",
        )
    )

    assert change.quantity == Decimal("-99999999.9999999999")
    assert change.price == Decimal("99999999.9999999999")
    assert change.amount == Decimal("99999999.9999999999")


@pytest.mark.parametrize(
    ("field_name", "value", "violation"),
    [
        ("quantity", "1.00000000001", "excess_scale"),
        ("price", "100000000.0000000000", "magnitude_overflow"),
        ("amount", "1.00000000001", "excess_scale"),
        ("price", "0.0000000000", "greater than 0"),
    ],
)
def test_simulation_change_rejects_unpersistable_values(
    field_name: str,
    value: str,
    violation: str,
) -> None:
    with pytest.raises(ValidationError, match=violation):
        SimulationChangeInput.model_validate(_change(**{field_name: value}))


@pytest.mark.parametrize("field_name", ["quantity", "price", "amount"])
def test_simulation_change_rejects_lossy_json_numbers(field_name: str) -> None:
    with pytest.raises(ValidationError, match="floating-point input is not permitted"):
        SimulationChangeInput.model_validate(_change(**{field_name: 0.1}))


@pytest.mark.parametrize("field_name", ["quantity", "price", "amount"])
def test_simulation_change_publishes_exact_numeric_schema(field_name: str) -> None:
    field_schema = SimulationChangeInput.model_json_schema()["properties"][field_name]

    assert "NUMERIC(18,10)" in field_schema["description"]
    assert (
        "excess scale and magnitude overflow are rejected, not rounded"
        in (field_schema["description"])
    )
    assert '"type": "number"' not in str(field_schema)
