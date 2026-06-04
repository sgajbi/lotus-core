from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.services.query_service.app.dtos.analytics_input_dto import CashFlowObservation
from src.services.query_service.app.services.analytics_cash_flows import (
    AnalyticsCashFlowError,
    build_cash_flow_observation,
    effective_beginning_market_value,
    portfolio_cash_flows_for_dates,
    position_cash_flows_for_keys,
)


def test_build_cash_flow_observation_normalizes_timing_control_code() -> None:
    row = SimpleNamespace(
        classification=" expense ",
        is_position_flow=True,
        is_portfolio_flow=False,
        timing=" EOD ",
    )

    observation = build_cash_flow_observation(row, amount=Decimal("-10"))

    assert observation.timing == "eod"
    assert observation.cash_flow_type == "fee"
    assert observation.flow_scope == "operational"
    assert observation.source_classification == " expense "


def test_portfolio_cash_flows_for_dates_requires_reporting_fx_when_needed() -> None:
    with pytest.raises(AnalyticsCashFlowError, match="Missing FX rate for EUR/USD"):
        portfolio_cash_flows_for_dates(
            [
                SimpleNamespace(
                    valuation_date=date(2025, 1, 1),
                    amount=Decimal("5"),
                    classification="CASHFLOW_IN",
                    timing="BOD",
                    is_position_flow=True,
                    is_portfolio_flow=True,
                )
            ],
            reporting_currency="USD",
            portfolio_currency="EUR",
            fx_rates={},
        )


def test_position_cash_flows_for_keys_preserves_non_position_amounts() -> None:
    result = position_cash_flows_for_keys(
        [
            SimpleNamespace(
                security_id="SEC_A",
                valuation_date=date(2025, 1, 1),
                amount=Decimal("5"),
                classification="TRANSFER",
                timing="BOD",
                is_position_flow=False,
                is_portfolio_flow=True,
            )
        ]
    )

    observation = result[("SEC_A", date(2025, 1, 1))][0]
    assert observation.amount == Decimal("5")
    assert observation.cash_flow_type == "transfer"


def test_effective_beginning_market_value_keeps_cash_book_fee_drag_explicit() -> None:
    row = SimpleNamespace(
        security_id="CASH_USD_BOOK_OPERATING",
        asset_class="Cash",
        bod_market_value=Decimal("100"),
        eod_market_value=Decimal("99.725"),
        bod_cashflow_position=Decimal("0"),
    )
    fee_flow = CashFlowObservation(
        amount=Decimal("-0.275"),
        timing="eod",
        cash_flow_type="fee",
        flow_scope="operational",
        source_classification="EXPENSE",
    )

    result = effective_beginning_market_value(
        row,
        previous_eod_market_value=Decimal("100"),
        cash_flows=[fee_flow],
        has_portfolio_external_flow=False,
    )

    assert result == Decimal("100")


def test_effective_beginning_market_value_normalizes_cash_book_asset_class() -> None:
    row = SimpleNamespace(
        security_id="OPERATING_ACCOUNT_USD",
        asset_class=" cash ",
        bod_market_value=Decimal("0"),
        eod_market_value=Decimal("250"),
        bod_cashflow_position=Decimal("200"),
    )
    internal_flow = CashFlowObservation(
        amount=Decimal("-200"),
        timing="bod",
        cash_flow_type="internal_trade_flow",
        flow_scope="internal",
        source_classification="INVESTMENT_OUTFLOW",
    )

    result = effective_beginning_market_value(
        row,
        previous_eod_market_value=Decimal("100"),
        cash_flows=[internal_flow],
        has_portfolio_external_flow=False,
    )

    assert result == Decimal("250")
