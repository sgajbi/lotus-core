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
        "transaction_type": f" {transaction_type.lower()} ",
        "portfolio_id": "PB_SG_GLOBAL_BAL_001",
        "instrument_id": "EQ_US_AAPL",
        "security_id": "AAPL",
        "transaction_date": datetime(2026, 1, 2, 10, 0),
        "quantity": Decimal("10"),
        "price": Decimal("100"),
        "gross_transaction_amount": Decimal("1000"),
        "trade_currency": "USD",
        "currency": "SGD",
    }


@pytest.mark.parametrize(
    ("model_type", "transaction_type"),
    [
        (BuyCanonicalTransaction, "BUY"),
        (SellCanonicalTransaction, "SELL"),
        (DividendCanonicalTransaction, "DIVIDEND"),
        (InterestCanonicalTransaction, "INTEREST"),
    ],
)
def test_cash_security_models_normalize_transaction_type(
    model_type, transaction_type: str
) -> None:
    txn = model_type.model_validate(_cash_security_record(transaction_type))

    assert txn.transaction_type == transaction_type


def test_dividend_model_normalizes_cash_entry_mode_without_defaulting() -> None:
    txn = DividendCanonicalTransaction.model_validate(
        _cash_security_record("DIVIDEND") | {"cash_entry_mode": " upstream_provided "}
    )
    implicit_txn = DividendCanonicalTransaction.model_validate(_cash_security_record("DIVIDEND"))

    assert txn.cash_entry_mode == "UPSTREAM_PROVIDED"
    assert implicit_txn.cash_entry_mode is None


def test_interest_model_normalizes_interest_direction_and_cash_entry_mode() -> None:
    txn = InterestCanonicalTransaction.model_validate(
        _cash_security_record("INTEREST")
        | {"interest_direction": " expense ", "cash_entry_mode": " auto_generate "}
    )

    assert txn.interest_direction == "EXPENSE"
    assert txn.cash_entry_mode == "AUTO_GENERATE"


def test_fx_transaction_model_normalizes_control_codes() -> None:
    txn = FxCanonicalTransaction.model_validate(
        {
            "transaction_id": "FX_001",
            "transaction_type": " fx_forward ",
            "component_type": " fx_cash_settlement_buy ",
            "component_id": "FX_001_BUY",
            "portfolio_id": "PB_SG_GLOBAL_BAL_001",
            "instrument_id": "FX_EUR_USD_001",
            "security_id": "FX_EUR_USD_001",
            "transaction_date": datetime(2026, 1, 2, 10, 0),
            "quantity": Decimal("0"),
            "price": Decimal("0"),
            "gross_transaction_amount": Decimal("0"),
            "trade_currency": "EUR",
            "currency": "USD",
            "pair_base_currency": "EUR",
            "pair_quote_currency": "USD",
            "fx_rate_quote_convention": " quote_per_base ",
            "buy_currency": "USD",
            "sell_currency": "EUR",
            "buy_amount": Decimal("108000"),
            "sell_amount": Decimal("100000"),
            "contract_rate": Decimal("1.08"),
            "fx_cash_leg_role": " buy ",
            "settlement_status": " settled ",
            "spot_exposure_model": " fx_contract ",
            "fx_realized_pnl_mode": " upstream_provided ",
        }
    )

    assert txn.transaction_type == "FX_FORWARD"
    assert txn.component_type == "FX_CASH_SETTLEMENT_BUY"
    assert txn.fx_rate_quote_convention == "QUOTE_PER_BASE"
    assert txn.fx_cash_leg_role == "BUY"
    assert txn.settlement_status == "SETTLED"
    assert txn.spot_exposure_model == "FX_CONTRACT"
    assert txn.fx_realized_pnl_mode == "UPSTREAM_PROVIDED"


def test_fx_transaction_model_preserves_implicit_optional_modes() -> None:
    txn = FxCanonicalTransaction.model_validate(
        {
            "transaction_id": "FX_002",
            "transaction_type": "FX_SPOT",
            "component_type": "FX_CONTRACT_OPEN",
            "component_id": "FX_002_OPEN",
            "portfolio_id": "PB_SG_GLOBAL_BAL_001",
            "instrument_id": "FX_EUR_USD_002",
            "security_id": "FX_EUR_USD_002",
            "transaction_date": datetime(2026, 1, 2, 10, 0),
            "quantity": Decimal("0"),
            "price": Decimal("0"),
            "gross_transaction_amount": Decimal("0"),
            "trade_currency": "EUR",
            "currency": "USD",
            "pair_base_currency": "EUR",
            "pair_quote_currency": "USD",
            "fx_rate_quote_convention": "QUOTE_PER_BASE",
            "buy_currency": "USD",
            "sell_currency": "EUR",
            "buy_amount": Decimal("108000"),
            "sell_amount": Decimal("100000"),
            "contract_rate": Decimal("1.08"),
        }
    )

    assert txn.fx_cash_leg_role is None
    assert txn.settlement_status is None
    assert txn.spot_exposure_model is None
    assert txn.fx_realized_pnl_mode is None
