from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.services.query_control_plane_service.app.application.analytics.analytics_cash_flows import (  # noqa: E501
    AnalyticsCashFlowError,
    build_cash_flow_observation,
    effective_beginning_market_value,
    is_cash_book_position,
    portfolio_cash_flows_for_dates,
    position_cash_flows_for_keys,
)
from src.services.query_control_plane_service.app.contracts.analytics_inputs import (
    CashFlowObservation,
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


@pytest.mark.parametrize(
    ("prior_close", "income", "current_close"),
    [
        ("102585", "850", "103435"),
        ("143435", "1187", "144622"),
    ],
)
def test_internal_income_receipt_preserves_authoritative_cash_open(
    prior_close: str, income: str, current_close: str
) -> None:
    """A BOD cash receipt is not already invested at the prior close.

    The durable position-timeseries beginning value and previous EOD agree;
    replacing them with today's post-receipt close erases income return and
    creates a false negative cash-sleeve return.
    """
    row = SimpleNamespace(
        security_id="CASH_USD_BOOK_OPERATING",
        asset_class="Cash",
        bod_market_value=Decimal(prior_close),
        eod_market_value=Decimal(current_close),
        bod_cashflow_position=Decimal(income),
    )
    receipt = CashFlowObservation(
        amount=Decimal(income),
        timing="bod",
        cash_flow_type="internal_trade_flow",
        flow_scope="internal",
        source_classification="INVESTMENT_OUTFLOW",
    )

    assert effective_beginning_market_value(
        row,
        previous_eod_market_value=Decimal(prior_close),
        cash_flows=[receipt],
        has_portfolio_external_flow=False,
    ) == Decimal(prior_close)

    # With no external portfolio flow, source close-to-close wealth includes
    # the income. The cash leg alone is a zero-return internal transfer.
    assert Decimal(current_close) - Decimal(prior_close) == Decimal(income)


@pytest.mark.parametrize("prior_close", [None, Decimal("0")])
@pytest.mark.parametrize("snapshot_bod_flow", [Decimal("77528.75"), Decimal("0")])
def test_new_internally_funded_holding_keeps_zero_source_open(
    prior_close: Decimal | None,
    snapshot_bod_flow: Decimal,
) -> None:
    row = SimpleNamespace(
        security_id="FO_EQ_AAPL_US",
        asset_class="Equity",
        bod_market_value=Decimal("0"),
        eod_market_value=Decimal("77374.08"),
        bod_cashflow_position=snapshot_bod_flow,
    )
    acquisition = CashFlowObservation(
        amount=Decimal("77528.75"),
        timing="bod",
        cash_flow_type="internal_trade_flow",
        flow_scope="internal",
        source_classification="INVESTMENT_OUTFLOW",
    )

    assert effective_beginning_market_value(
        row,
        previous_eod_market_value=prior_close,
        cash_flows=[acquisition],
        has_portfolio_external_flow=False,
    ) == Decimal("0")


@pytest.mark.parametrize(
    ("timing", "classification"),
    [("eod", "INVESTMENT_OUTFLOW"), ("bod", "INVESTMENT_INFLOW")],
)
def test_zero_open_without_trade_date_acquisition_keeps_conservative_fallback(
    timing: str, classification: str
) -> None:
    row = SimpleNamespace(
        security_id="FO_EQ_AAPL_US",
        asset_class="Equity",
        bod_market_value=Decimal("0"),
        eod_market_value=Decimal("49"),
        bod_cashflow_position=Decimal("0"),
    )
    unrelated_flow = CashFlowObservation(
        amount=Decimal("50"),
        timing=timing,
        cash_flow_type="internal_trade_flow",
        flow_scope="internal",
        source_classification=classification,
    )

    assert effective_beginning_market_value(
        row,
        previous_eod_market_value=None,
        cash_flows=[unrelated_flow],
        has_portfolio_external_flow=False,
    ) == Decimal("49")


@pytest.mark.parametrize("prior_close", [None, Decimal("0")])
def test_first_day_internal_cash_settlement_keeps_sourced_zero_open(
    prior_close: Decimal | None,
) -> None:
    row = SimpleNamespace(
        security_id="CASH_USD_SETTLEMENT",
        asset_class="Cash",
        bod_market_value=Decimal("0"),
        eod_market_value=Decimal("-1000"),
        bod_cashflow_position=Decimal("0"),
    )
    settlement = CashFlowObservation(
        amount=Decimal("-1000"),
        timing="eod",
        cash_flow_type="internal_trade_flow",
        flow_scope="internal",
        source_classification="TRANSFER",
    )

    assert effective_beginning_market_value(
        row,
        previous_eod_market_value=prior_close,
        cash_flows=[settlement],
        has_portfolio_external_flow=False,
    ) == Decimal("0")


def test_unreconciled_first_day_cash_settlement_keeps_conservative_fallback() -> None:
    row = SimpleNamespace(
        security_id="CASH_USD_SETTLEMENT",
        asset_class="Cash",
        bod_market_value=Decimal("0"),
        eod_market_value=Decimal("-900"),
        bod_cashflow_position=Decimal("0"),
    )
    settlement = CashFlowObservation(
        amount=Decimal("-1000"),
        timing="eod",
        cash_flow_type="internal_trade_flow",
        flow_scope="internal",
        source_classification="TRANSFER",
    )

    assert effective_beginning_market_value(
        row,
        previous_eod_market_value=None,
        cash_flows=[settlement],
        has_portfolio_external_flow=False,
    ) == Decimal("-900")


@pytest.mark.parametrize(
    ("flow", "classification"),
    [("850", "INVESTMENT_OUTFLOW"), ("-100", "INVESTMENT_INFLOW")],
)
def test_existing_zero_balance_cash_book_keeps_correlated_zero_open(
    flow: str, classification: str
) -> None:
    row = SimpleNamespace(
        security_id="CASH_USD_BOOK_OPERATING",
        asset_class="Cash",
        bod_market_value=Decimal("0"),
        eod_market_value=Decimal(flow),
        bod_cashflow_position=Decimal(flow),
    )
    receipt = CashFlowObservation(
        amount=Decimal(flow),
        timing="bod",
        cash_flow_type="internal_trade_flow",
        flow_scope="internal",
        source_classification=classification,
    )

    assert effective_beginning_market_value(
        row,
        previous_eod_market_value=Decimal("0"),
        cash_flows=[receipt],
        has_portfolio_external_flow=False,
    ) == Decimal("0")


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


@pytest.mark.parametrize(
    ("security_id", "product_type", "asset_class", "expected"),
    [
        ("CASH_PREFIXED_EQUITY", "EQUITY", "Equity", False),
        ("OPERATING_ACCOUNT_USD", None, " cash ", True),
        ("OPERATING_ACCOUNT_USD", " cash ", None, True),
    ],
)
def test_cash_book_position_uses_product_metadata_not_identifier_shape(
    security_id: str,
    product_type: str | None,
    asset_class: str | None,
    expected: bool,
) -> None:
    row = SimpleNamespace(
        security_id=security_id,
        product_type=product_type,
        asset_class=asset_class,
    )

    assert is_cash_book_position(row) is expected


def test_product_type_cash_preserves_internal_cash_book_beginning_value() -> None:
    row = SimpleNamespace(
        security_id="OPERATING_ACCOUNT_USD",
        product_type="CASH",
        asset_class=None,
        bod_market_value=Decimal("80"),
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

    assert effective_beginning_market_value(
        row,
        previous_eod_market_value=Decimal("100"),
        cash_flows=[internal_flow],
        has_portfolio_external_flow=False,
    ) == Decimal("250")
