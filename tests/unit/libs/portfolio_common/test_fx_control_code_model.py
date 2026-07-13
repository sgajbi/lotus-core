from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from portfolio_common.transaction_domain.fx_models import FxCanonicalTransaction


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
