from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from portfolio_common.transaction_type_registry import TRANSACTION_TYPE_REGISTRY

from src.services.portfolio_transaction_processing_service.app.application import (
    build_cost_basis_timeline_processor,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    AverageCostBasisStrategy,
    CostBasisTransaction,
)

AVCO_LOT_INFLOW_TYPES = {
    "MERGER_IN",
    "EXCHANGE_IN",
    "REPLACEMENT_IN",
    "SPIN_IN",
    "DEMERGER_IN",
    "RIGHTS_ALLOCATE",
    "RIGHTS_SHARE_DELIVERY",
}
AVCO_LOT_OUTFLOW_TYPES = {
    "MERGER_OUT",
    "EXCHANGE_OUT",
    "REPLACEMENT_OUT",
    "CASH_IN_LIEU",
    "RIGHTS_EXPIRE",
    "RIGHTS_SELL",
    "RIGHTS_SUBSCRIBE",
    "RIGHTS_OVERSUBSCRIBE",
}
AVCO_PARTIAL_BASIS_TRANSFER_TYPES = {"SPIN_OFF", "DEMERGER_OUT"}
AVCO_QUANTITY_RESTATEMENT_TYPES = {
    "SPLIT",
    "REVERSE_SPLIT",
    "CONSOLIDATION",
    "BONUS_ISSUE",
    "STOCK_DIVIDEND",
}
AVCO_NON_LOT_TYPES = {
    "CASH_CONSIDERATION",
    "RIGHTS_ANNOUNCE",
    "RIGHTS_ADJUSTMENT",
    "RIGHTS_REFUND",
}


def _raw_transaction(
    *,
    transaction_id: str,
    transaction_type: str,
    transaction_date: str,
    quantity: str,
    gross_amount: str,
    price: str = "0",
    **extra_fields: str,
) -> dict[str, str]:
    return {
        "transaction_id": transaction_id,
        "portfolio_id": "P-AVCO-MATRIX",
        "instrument_id": "I-AVCO-MATRIX",
        "security_id": "S-AVCO-MATRIX",
        "transaction_date": transaction_date,
        "transaction_type": transaction_type,
        "quantity": quantity,
        "price": price,
        "gross_transaction_amount": gross_amount,
        "trade_currency": "USD",
        "portfolio_base_currency": "USD",
        "transaction_fx_rate": "1",
        "trade_fee": "0",
        **extra_fields,
    }


def _seed_buy() -> dict[str, str]:
    return _raw_transaction(
        transaction_id="AVCO-MATRIX-SEED-BUY",
        transaction_type="BUY",
        transaction_date="2026-01-01T00:00:00Z",
        quantity="100",
        gross_amount="1000",
        price="10",
    )


def _process(*transactions: dict[str, str]):
    return build_cost_basis_timeline_processor("AVCO").process_transactions([], list(transactions))


def _source_values(states):
    return {
        source_transaction_id: (
            state.quantity,
            state.cost_local,
            state.cost_base,
        )
        for source_transaction_id, state in states.items()
    }


def test_avco_matrix_classifies_every_production_corporate_action_and_rights_type() -> None:
    governed_types = {
        code
        for code, definition in TRANSACTION_TYPE_REGISTRY.items()
        if definition.production_booking_allowed
        and definition.lifecycle_family in {"corporate_action", "rights"}
    }
    classified_types = (
        AVCO_LOT_INFLOW_TYPES
        | AVCO_LOT_OUTFLOW_TYPES
        | AVCO_PARTIAL_BASIS_TRANSFER_TYPES
        | AVCO_QUANTITY_RESTATEMENT_TYPES
        | AVCO_NON_LOT_TYPES
    )

    assert classified_types == governed_types


@pytest.mark.parametrize("transaction_type", sorted(AVCO_LOT_INFLOW_TYPES | {"TRANSFER_IN"}))
def test_avco_lot_inflow_families_open_source_basis(transaction_type: str) -> None:
    processed, errors, states = _process(
        _raw_transaction(
            transaction_id=f"{transaction_type}-SOURCE",
            transaction_type=transaction_type,
            transaction_date="2026-01-01T00:00:00Z",
            quantity="100",
            gross_amount="1000",
            price="10",
        )
    )

    assert not errors
    assert len(processed) == 1
    assert _source_values(states) == {
        f"{transaction_type}-SOURCE": (
            Decimal("100"),
            Decimal("1000"),
            Decimal("1000"),
        )
    }


@pytest.mark.parametrize("transaction_type", sorted(AVCO_LOT_OUTFLOW_TYPES | {"TRANSFER_OUT"}))
def test_avco_lot_outflow_families_consume_source_basis(transaction_type: str) -> None:
    gross_amount = "600" if transaction_type == "CASH_IN_LIEU" else "0"
    cash_in_lieu_fields = (
        {
            "allocated_cost_basis_local": "400",
            "allocated_cost_basis_base": "400",
        }
        if transaction_type == "CASH_IN_LIEU"
        else {}
    )
    processed, errors, states = _process(
        _seed_buy(),
        _raw_transaction(
            transaction_id=f"{transaction_type}-EVENT",
            transaction_type=transaction_type,
            transaction_date="2026-01-02T00:00:00Z",
            quantity="40",
            gross_amount=gross_amount,
            **cash_in_lieu_fields,
        ),
    )

    assert not errors
    assert len(processed) == 2
    assert _source_values(states) == {
        "AVCO-MATRIX-SEED-BUY": (
            Decimal("60"),
            Decimal("600"),
            Decimal("600"),
        )
    }
    outflow = processed[-1]
    assert outflow.net_cost == Decimal("-400")
    assert outflow.net_cost_local == Decimal("-400")
    if transaction_type == "CASH_IN_LIEU":
        assert outflow.realized_gain_loss == Decimal("200")
    else:
        assert outflow.realized_gain_loss is None


@pytest.mark.parametrize("transaction_type", sorted(AVCO_PARTIAL_BASIS_TRANSFER_TYPES))
def test_avco_partial_basis_transfers_consume_quantity_when_present(
    transaction_type: str,
) -> None:
    processed, errors, states = _process(
        _seed_buy(),
        _raw_transaction(
            transaction_id=f"{transaction_type}-QUANTITY",
            transaction_type=transaction_type,
            transaction_date="2026-01-02T00:00:00Z",
            quantity="40",
            gross_amount="0",
        ),
    )

    assert not errors
    assert processed[-1].net_cost == Decimal("-400")
    assert states["AVCO-MATRIX-SEED-BUY"].quantity == Decimal("60")


@pytest.mark.parametrize("transaction_type", sorted(AVCO_PARTIAL_BASIS_TRANSFER_TYPES))
def test_avco_basis_only_transfers_preserve_source_quantity(transaction_type: str) -> None:
    processed, errors, states = _process(
        _seed_buy(),
        _raw_transaction(
            transaction_id=f"{transaction_type}-BASIS-ONLY",
            transaction_type=transaction_type,
            transaction_date="2026-01-02T00:00:00Z",
            quantity="0",
            gross_amount="100",
        ),
    )

    assert not errors
    assert processed[-1].net_cost == Decimal("-100")
    assert _source_values(states)["AVCO-MATRIX-SEED-BUY"] == (
        Decimal("100"),
        Decimal("900"),
        Decimal("900"),
    )


@pytest.mark.parametrize("transaction_type", sorted(AVCO_QUANTITY_RESTATEMENT_TYPES))
def test_avco_quantity_restatements_preserve_source_basis(transaction_type: str) -> None:
    processed, errors, states = _process(
        _seed_buy(),
        _raw_transaction(
            transaction_id=f"{transaction_type}-EVENT",
            transaction_type=transaction_type,
            transaction_date="2026-01-02T00:00:00Z",
            quantity="20",
            gross_amount="0",
        ),
    )

    assert not errors
    assert processed[-1].net_cost == Decimal("0")
    assert _source_values(states)["AVCO-MATRIX-SEED-BUY"] == (
        Decimal("100"),
        Decimal("1000"),
        Decimal("1000"),
    )


@pytest.mark.parametrize("transaction_type", sorted(AVCO_NON_LOT_TYPES))
def test_avco_non_lot_corporate_action_and_rights_events_preserve_sources(
    transaction_type: str,
) -> None:
    event = _raw_transaction(
        transaction_id=f"{transaction_type}-EVENT",
        transaction_type=transaction_type,
        transaction_date="2026-01-02T00:00:00Z",
        quantity="0",
        gross_amount="100" if transaction_type in {"CASH_CONSIDERATION", "RIGHTS_REFUND"} else "0",
    )
    if transaction_type == "CASH_CONSIDERATION":
        event.update(
            allocated_cost_basis_local="40",
            allocated_cost_basis_base="40",
        )

    processed, errors, states = _process(
        _seed_buy(),
        event,
    )

    assert not errors
    assert len(processed) == 2
    assert _source_values(states)["AVCO-MATRIX-SEED-BUY"] == (
        Decimal("100"),
        Decimal("1000"),
        Decimal("1000"),
    )
    if transaction_type == "CASH_CONSIDERATION":
        assert processed[-1].realized_capital_pnl_base == Decimal("60")
        assert processed[-1].realized_fx_pnl_base == Decimal(0)
        assert processed[-1].realized_total_pnl_base == Decimal("60")


def test_avco_fee_inclusive_cross_currency_sources_reconcile_local_and_base_cost() -> None:
    strategy = AverageCostBasisStrategy()
    for transaction_id, quantity, local_cost, base_cost in (
        ("EUR-FEE-BUY-1", "100", "1005", "1105.5"),
        ("EUR-FEE-BUY-2", "50", "605", "696"),
    ):
        strategy.add_buy_lot(
            CostBasisTransaction(
                transaction_id=transaction_id,
                portfolio_id="P-SGD",
                instrument_id="EUR-FUND",
                security_id="S-EUR-FUND",
                transaction_type="BUY",
                transaction_date=datetime(2026, 1, 1),
                quantity=Decimal(quantity),
                gross_transaction_amount=Decimal(local_cost),
                net_cost_local=Decimal(local_cost),
                net_cost=Decimal(base_cost),
                trade_currency="EUR",
                portfolio_base_currency="SGD",
            )
        )

    cogs_base, cogs_local, consumed, error = strategy.consume_sell_quantity(
        "P-SGD", "EUR-FUND", Decimal("60")
    )

    assert error is None
    assert consumed == Decimal("60")
    assert cogs_local == Decimal("644")
    assert cogs_base == Decimal("720.6")
    states = strategy.get_open_lot_states()
    assert _source_values(states) == {
        "EUR-FEE-BUY-1": (
            Decimal("60.0000000000"),
            Decimal("603.0"),
            Decimal("663.30"),
        ),
        "EUR-FEE-BUY-2": (
            Decimal("30.0000000000"),
            Decimal("363.0"),
            Decimal("417.60"),
        ),
    }


def test_avco_source_allocation_is_isolated_by_portfolio_and_instrument() -> None:
    strategy = AverageCostBasisStrategy()
    for portfolio_id, instrument_id, transaction_id, cost in (
        ("P1", "EQUITY-A", "P1-A-BUY", "1000"),
        ("P1", "BOND-B", "P1-B-BUY", "1200"),
        ("P2", "EQUITY-A", "P2-A-BUY", "1500"),
    ):
        strategy.add_buy_lot(
            CostBasisTransaction(
                transaction_id=transaction_id,
                portfolio_id=portfolio_id,
                instrument_id=instrument_id,
                security_id=instrument_id,
                transaction_type="BUY",
                transaction_date=datetime(2026, 1, 1),
                quantity=Decimal("100"),
                gross_transaction_amount=Decimal(cost),
                net_cost_local=Decimal(cost),
                net_cost=Decimal(cost),
                trade_currency="USD",
                portfolio_base_currency="USD",
            )
        )

    strategy.consume_sell_quantity("P1", "EQUITY-A", Decimal("40"))

    states = strategy.get_open_lot_states()
    assert states["P1-A-BUY"].quantity == Decimal("60")
    assert states["P1-B-BUY"].quantity == Decimal("100")
    assert states["P2-A-BUY"].quantity == Decimal("100")
