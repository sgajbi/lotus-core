from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction.fx import (
    UnsupportedFxRealizedPnlModeError,
    build_fx_processed_transaction,
)


def _fx_transaction(**updates: object) -> BookedTransaction:
    transaction = BookedTransaction(
        transaction_id="FX-BASELINE-001",
        portfolio_id="PORT-FX-1",
        instrument_id="FXC-EURUSD-001",
        security_id="FXC-EURUSD-001",
        transaction_date=datetime(2026, 4, 1, 9, 0, 0),
        settlement_date=datetime(2026, 7, 1, 0, 0, 0),
        transaction_type="FX_FORWARD",
        component_type="FX_CONTRACT_CLOSE",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("0"),
        trade_currency="USD",
        currency="USD",
        pair_base_currency="EUR",
        pair_quote_currency="USD",
        buy_currency="USD",
        sell_currency="EUR",
        buy_amount=Decimal("1095000"),
        sell_amount=Decimal("1000000"),
        contract_rate=Decimal("1.095"),
        fx_contract_id="FXC-2026-0001",
        fx_realized_pnl_mode="NONE",
    )
    return replace(transaction, **updates)


def test_build_fx_processed_transaction_normalizes_none_realized_pnl_mode() -> None:
    transaction = _fx_transaction(
        fx_realized_pnl_mode=" none ",
        realized_capital_pnl_local=Decimal("10"),
        realized_fx_pnl_local=Decimal("20"),
        realized_total_pnl_local=Decimal("30"),
        realized_capital_pnl_base=Decimal("10"),
        realized_fx_pnl_base=Decimal("20"),
        realized_total_pnl_base=Decimal("30"),
    )

    processed = build_fx_processed_transaction(transaction)

    assert processed.fx_realized_pnl_mode == "NONE"
    assert processed.realized_capital_pnl_local == Decimal("0")
    assert processed.realized_fx_pnl_local == Decimal("0")
    assert processed.realized_total_pnl_local == Decimal("0")
    assert processed.realized_capital_pnl_base == Decimal("0")
    assert processed.realized_fx_pnl_base == Decimal("0")
    assert processed.realized_total_pnl_base == Decimal("0")


def test_build_fx_processed_transaction_normalizes_upstream_provided_mode() -> None:
    transaction = _fx_transaction(
        fx_realized_pnl_mode=" upstream_provided ",
        realized_capital_pnl_local=Decimal("0"),
        realized_fx_pnl_local=Decimal("20"),
        realized_capital_pnl_base=Decimal("0"),
        realized_fx_pnl_base=Decimal("25"),
    )

    processed = build_fx_processed_transaction(transaction)

    assert processed.fx_realized_pnl_mode == "UPSTREAM_PROVIDED"
    assert processed.realized_total_pnl_local == Decimal("20")
    assert processed.realized_total_pnl_base == Decimal("25")


def test_build_fx_processed_transaction_rejects_unsupported_cash_lot_mode() -> None:
    transaction = _fx_transaction(fx_realized_pnl_mode=" cash_lot_cost_method ")

    with pytest.raises(
        UnsupportedFxRealizedPnlModeError,
        match="CASH_LOT_COST_METHOD.*supported modes are NONE and UPSTREAM_PROVIDED",
    ):
        build_fx_processed_transaction(transaction)
