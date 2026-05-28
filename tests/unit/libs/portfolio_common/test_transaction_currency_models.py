from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from portfolio_common.transaction_domain.buy_models import BuyCanonicalTransaction
from portfolio_common.transaction_domain.dividend_models import DividendCanonicalTransaction
from portfolio_common.transaction_domain.fx_models import FxCanonicalTransaction
from portfolio_common.transaction_domain.interest_models import InterestCanonicalTransaction
from portfolio_common.transaction_domain.sell_models import SellCanonicalTransaction


def _cash_security_record(transaction_type: str) -> dict[str, object]:
    return {
        "transaction_id": f"{transaction_type}_001",
        "transaction_type": transaction_type,
        "portfolio_id": "PB_SG_GLOBAL_BAL_001",
        "instrument_id": "EQ_US_AAPL",
        "security_id": "AAPL",
        "transaction_date": datetime(2026, 1, 2, 10, 0),
        "quantity": Decimal("10"),
        "price": Decimal("100"),
        "gross_transaction_amount": Decimal("1000"),
        "trade_currency": " usd ",
        "currency": " sgd ",
    }


@pytest.mark.parametrize(
    "model_type",
    [
        BuyCanonicalTransaction,
        SellCanonicalTransaction,
        DividendCanonicalTransaction,
        InterestCanonicalTransaction,
    ],
)
def test_cash_security_transaction_models_normalize_currencies(model_type) -> None:
    transaction_type = model_type.__name__.split("Canonical")[0]

    txn = model_type.model_validate(_cash_security_record(transaction_type))

    assert txn.trade_currency == "USD"
    assert txn.currency == "SGD"


def test_fx_transaction_model_normalizes_currency_fields() -> None:
    txn = FxCanonicalTransaction.model_validate(
        {
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
