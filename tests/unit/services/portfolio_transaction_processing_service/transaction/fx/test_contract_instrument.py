from dataclasses import replace
from datetime import datetime
from decimal import Decimal

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction.fx import (
    build_fx_contract_instrument,
)


def _fx_contract_transaction() -> BookedTransaction:
    return BookedTransaction(
        transaction_id="FX-OPEN-001",
        portfolio_id="PORT-FX-1",
        instrument_id="TEMP-INST",
        security_id="TEMP-SEC",
        transaction_date=datetime(2026, 4, 1, 9, 0, 0),
        settlement_date=datetime(2026, 7, 1, 0, 0, 0),
        transaction_type="FX_FORWARD",
        component_type="FX_CONTRACT_OPEN",
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
    )


def test_build_fx_contract_instrument_from_contract_component() -> None:
    transaction = replace(
        _fx_contract_transaction(),
        component_type=" fx_contract_open ",
        buy_currency=" usd ",
        sell_currency=" eur ",
    )
    instrument = build_fx_contract_instrument(transaction)

    assert instrument is not None
    assert instrument.security_id == "FXC-2026-0001"
    assert instrument.product_type == "FX_CONTRACT"
    assert instrument.asset_class == "FX"
    assert instrument.portfolio_id == "PORT-FX-1"
    assert instrument.trade_date.isoformat() == "2026-04-01"
    assert instrument.maturity_date.isoformat() == "2026-07-01"
    assert instrument.pair_base_currency == "EUR"
    assert instrument.pair_quote_currency == "USD"
    assert instrument.currency == "USD"
    assert instrument.buy_currency == "USD"
    assert instrument.sell_currency == "EUR"
    assert instrument.buy_amount == Decimal("1095000")
    assert instrument.contract_rate == Decimal("1.095")


def test_build_fx_contract_instrument_returns_none_for_cash_component() -> None:
    transaction = replace(_fx_contract_transaction(), component_type=" fx_cash_settlement_buy ")
    assert build_fx_contract_instrument(transaction) is None
