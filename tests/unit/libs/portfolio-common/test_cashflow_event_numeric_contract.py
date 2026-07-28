from decimal import Decimal

import pytest
from portfolio_common.events import CashflowCalculatedEvent
from pydantic import ValidationError


def _event(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "cashflow_id": 1,
        "transaction_id": "TXN-1",
        "portfolio_id": "PORT-1",
        "cashflow_date": "2026-07-29",
        "amount": "100.0000000000",
        "currency": "USD",
        "classification": "INVESTMENT_INFLOW",
        "timing": "EOD",
        "is_position_flow": True,
        "is_portfolio_flow": False,
        "calculation_type": "NET",
    }
    payload.update(overrides)
    return payload


def test_cashflow_event_preserves_exact_amount() -> None:
    event = CashflowCalculatedEvent.model_validate(_event(amount="-99999999.9999999999"))

    assert event.amount == Decimal("-99999999.9999999999")


@pytest.mark.parametrize(
    ("value", "violation"),
    [
        ("1.00000000001", "excess_scale"),
        ("100000000.0000000000", "magnitude_overflow"),
        ("NaN", "finite number"),
        (0.1, "floating-point input is not permitted"),
    ],
)
def test_cashflow_event_rejects_unpersistable_amount(
    value: object,
    violation: str,
) -> None:
    with pytest.raises(ValidationError, match=violation):
        CashflowCalculatedEvent.model_validate(_event(amount=value))
