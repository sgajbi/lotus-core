from decimal import Decimal

import pytest
from cost_engine.processing.cost_objects import OpenLotState

from src.services.calculators.cost_calculator_service.app.average_cost_pool_checkpoint import (
    AVERAGE_COST_POOL_STATE_VERSION,
    AverageCostPoolCheckpoint,
)


def test_checkpoint_aggregates_source_states_and_uses_last_positive_source() -> None:
    checkpoint = AverageCostPoolCheckpoint.from_open_lot_states(
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        states_by_source_transaction_id={
            "BUY-1": OpenLotState(
                quantity=Decimal("4"),
                cost_local=Decimal("40"),
                cost_base=Decimal("44"),
            ),
            "BUY-2": OpenLotState(
                quantity=Decimal(0),
                cost_local=Decimal(0),
                cost_base=Decimal(0),
            ),
            "BUY-3": OpenLotState(
                quantity=Decimal("6"),
                cost_local=Decimal("72"),
                cost_base=Decimal("78"),
            ),
        },
    )

    assert checkpoint.representative_source_transaction_id == "BUY-3"
    aggregate_state = checkpoint.as_open_lot_state()
    assert (
        aggregate_state.quantity,
        aggregate_state.cost_local,
        aggregate_state.cost_base,
    ) == (
        Decimal("10"),
        Decimal("112"),
        Decimal("122"),
    )
    assert checkpoint.state_version == AVERAGE_COST_POOL_STATE_VERSION


def test_checkpoint_allows_fully_closed_pool_without_representative_source() -> None:
    checkpoint = AverageCostPoolCheckpoint.from_open_lot_states(
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        states_by_source_transaction_id={
            "BUY-1": OpenLotState(
                quantity=Decimal(0),
                cost_local=Decimal(0),
                cost_base=Decimal(0),
            )
        },
    )

    assert checkpoint.representative_source_transaction_id is None
    assert checkpoint.quantity == Decimal(0)


@pytest.mark.parametrize(
    "overrides",
    [
        {"quantity": Decimal("-1")},
        {"cost_local": Decimal("-1")},
        {"cost_base": Decimal("-1")},
        {"quantity": Decimal("1"), "representative_source_transaction_id": None},
        {"quantity": Decimal(0), "cost_local": Decimal("1")},
        {"quantity": Decimal(0), "cost_base": Decimal("1")},
    ],
)
def test_checkpoint_rejects_inconsistent_pool_state(overrides: dict[str, object]) -> None:
    payload: dict[str, object] = {
        "portfolio_id": "P1",
        "instrument_id": "I1",
        "security_id": "S1",
        "representative_source_transaction_id": "BUY-1",
        "quantity": Decimal("1"),
        "cost_local": Decimal("10"),
        "cost_base": Decimal("11"),
    }
    payload.update(overrides)

    with pytest.raises(ValueError):
        AverageCostPoolCheckpoint(**payload)


def test_checkpoint_compatibility_requires_version_and_book_identity() -> None:
    checkpoint = AverageCostPoolCheckpoint(
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        representative_source_transaction_id="BUY-1",
        quantity=Decimal("1"),
        cost_local=Decimal("10"),
        cost_base=Decimal("11"),
    )

    assert checkpoint.is_compatible(portfolio_id="P1", instrument_id="I1", security_id="S1")
    assert not checkpoint.is_compatible(portfolio_id="P2", instrument_id="I1", security_id="S1")
    assert not checkpoint.is_compatible(portfolio_id="P1", instrument_id="I2", security_id="S1")
    assert not checkpoint.is_compatible(portfolio_id="P1", instrument_id="I1", security_id="S2")
    assert not AverageCostPoolCheckpoint(
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        representative_source_transaction_id="BUY-1",
        quantity=Decimal("1"),
        cost_local=Decimal("10"),
        cost_base=Decimal("11"),
        state_version="stale",
    ).is_compatible(portfolio_id="P1", instrument_id="I1", security_id="S1")
