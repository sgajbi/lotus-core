from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable, cast

from tests.e2e.api_client import E2EApiClient
from tests.e2e.state_assertions import assert_positions_state, has_expected_valuation_snapshot


class StubE2EApiClient:
    def __init__(self, *, pending_payload: dict[str, Any], ready_payload: dict[str, Any]) -> None:
        self.pending_payload = pending_payload
        self.ready_payload = ready_payload
        self.requested_endpoint: str | None = None

    def poll_for_data(
        self,
        endpoint: str,
        validation_func: Callable[[Any], bool],
        timeout: int = 60,
        interval: int = 2,
        fail_message: str = "Polling timed out",
    ) -> dict[str, Any]:
        self.requested_endpoint = endpoint
        assert timeout == 180
        assert fail_message
        assert not validation_func(self.pending_payload)
        assert validation_func(self.ready_payload)
        return self.ready_payload


def test_assert_positions_state_treats_incomplete_valuations_as_pending() -> None:
    pending_payload = {
        "positions": [
            {
                "security_id": "SEC_DAIMLER",
                "quantity": "60",
                "cost_basis": "9900",
                "valuation": {"market_value": None},
            }
        ]
    }
    ready_payload = {
        "positions": [
            {
                "security_id": "SEC_DAIMLER",
                "quantity": "60",
                "cost_basis": "9900",
                "valuation": {"market_value": "12960"},
            }
        ]
    }
    client = StubE2EApiClient(pending_payload=pending_payload, ready_payload=ready_payload)

    assert_positions_state(
        cast(E2EApiClient, client),
        portfolio_id="E2E_DUAL_CURRENCY",
        as_of_date="2025-08-15",
        expected_positions={
            "SEC_DAIMLER": {
                "quantity": Decimal("60"),
                "cost_basis": Decimal("9900"),
                "market_value": Decimal("12960"),
            }
        },
    )

    assert (
        client.requested_endpoint == "/portfolios/E2E_DUAL_CURRENCY/positions?as_of_date=2025-08-15"
    )


def test_expected_valuation_snapshot_rejects_cost_basis_fallback_and_wrong_price() -> None:
    fallback_position = {
        "valuation": {
            "market_price": None,
            "market_value": "9900",
            "unrealized_gain_loss": "0",
        }
    }
    wrong_snapshot = {
        "valuation": {
            "market_price": "170",
            "market_value": "12240",
            "unrealized_gain_loss": "2340",
        }
    }

    for position in (fallback_position, wrong_snapshot):
        assert not has_expected_valuation_snapshot(
            position,
            market_price=Decimal("180"),
            required_fields=("market_value", "unrealized_gain_loss"),
        )


def test_expected_valuation_snapshot_accepts_exact_materialized_price() -> None:
    assert has_expected_valuation_snapshot(
        {
            "valuation": {
                "market_price": "180",
                "market_value": "12960",
                "unrealized_gain_loss": "3060",
            }
        },
        market_price=Decimal("180"),
        required_fields=("market_value", "unrealized_gain_loss"),
    )
