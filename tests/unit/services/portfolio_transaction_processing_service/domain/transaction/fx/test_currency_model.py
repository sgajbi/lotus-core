"""Test canonical FX currency-pair modeling."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from src.services.portfolio_transaction_processing_service.app.domain.transaction.fx import (
    FxCanonicalTransaction,
)


def test_fx_transaction_model_normalizes_currency_fields() -> None:
    txn = FxCanonicalTransaction(
        **{
            "transaction_id": "FX_001",
            "transaction_type": "FX_SPOT",
            "component_type": "FX_CONTRACT_OPEN",
            "component_id": "FX_001_OPEN",
            "portfolio_id": "PB_SG_GLOBAL_BAL_001",
            "instrument_id": "FX_EUR_USD_001",
            "security_id": "FX_EUR_USD_001",
            "transaction_date": datetime(2026, 1, 2, 10, 0),
            "quantity": Decimal("0"),
            "price": Decimal("0"),
            "gross_transaction_amount": Decimal("0"),
            "trade_currency": " eur ",
            "currency": " usd ",
            "pair_base_currency": " eur ",
            "pair_quote_currency": " usd ",
            "fx_rate_quote_convention": "QUOTE_PER_BASE",
            "buy_currency": " usd ",
            "sell_currency": " eur ",
            "buy_amount": Decimal("108000"),
            "sell_amount": Decimal("100000"),
            "contract_rate": Decimal("1.08"),
        }
    )

    assert txn.trade_currency == "EUR"
    assert txn.currency == "USD"
    assert txn.pair_base_currency == "EUR"
    assert txn.pair_quote_currency == "USD"
    assert txn.buy_currency == "USD"
    assert txn.sell_currency == "EUR"
