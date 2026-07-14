"""Verify canonical transaction-to-lot behavior classification."""

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    AVERAGE_COST_POOL_LOT_BEHAVIORS,
    INCREMENTAL_SAFE_LOT_BEHAVIORS,
    LOT_OPENING_BEHAVIORS,
    LOT_STATE_MUTATING_BEHAVIORS,
    STATE_DEPENDENT_LOT_BEHAVIORS,
    transaction_lot_behavior,
)


@pytest.mark.parametrize(
    ("transaction_type", "expected_behavior"),
    [
        (" buy ", "open_lot"),
        ("SELL", "consume_lot"),
        ("transfer_in", "preserve_or_restate_lot"),
        ("TRANSFER_OUT", "preserve_or_consume_lot"),
        ("merger_in", "transfer_basis_in"),
        ("MERGER_OUT", "transfer_basis_out"),
        (None, "unknown"),
        ("unsupported", "unknown"),
    ],
)
def test_transaction_lot_behavior_uses_governed_transaction_definitions(
    transaction_type: object,
    expected_behavior: str,
) -> None:
    assert transaction_lot_behavior(transaction_type) == expected_behavior


def test_lot_behavior_sets_express_incremental_and_average_cost_policy() -> None:
    assert {"open_lot", "transfer_basis_in"} <= LOT_OPENING_BEHAVIORS
    assert {"consume_lot", "transfer_basis_out"} <= LOT_STATE_MUTATING_BEHAVIORS
    assert "consume_lot" in STATE_DEPENDENT_LOT_BEHAVIORS
    assert "open_lot" not in STATE_DEPENDENT_LOT_BEHAVIORS
    assert INCREMENTAL_SAFE_LOT_BEHAVIORS == LOT_STATE_MUTATING_BEHAVIORS | {"none"}
    assert AVERAGE_COST_POOL_LOT_BEHAVIORS == {"open_lot", "consume_lot"}
