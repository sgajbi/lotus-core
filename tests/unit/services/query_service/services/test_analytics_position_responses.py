from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.dtos.analytics_input_dto import CashFlowObservation
from src.services.query_service.app.services.analytics_position_responses import (
    position_response_row,
    position_response_rows,
)


def _position_row(
    *,
    valuation_date: date,
    security_id: str = "SEC_A",
    bod_market_value: Decimal = Decimal("100"),
    eod_market_value: Decimal = Decimal("110"),
    epoch: int = 0,
    position_currency: str = "EUR",
) -> SimpleNamespace:
    return SimpleNamespace(
        security_id=security_id,
        valuation_date=valuation_date,
        bod_market_value=bod_market_value,
        eod_market_value=eod_market_value,
        bod_cashflow_position=Decimal("0"),
        quantity=Decimal("2"),
        epoch=epoch,
        position_currency=position_currency,
        asset_class="Equity",
        sector="Technology",
        country="DE",
    )


def test_position_response_row_converts_values_and_projects_dimensions() -> None:
    support_inputs = SimpleNamespace(
        position_cashflows_by_key={},
        portfolio_cashflows_by_date={},
        position_to_portfolio_rates={"EUR": {date(2025, 1, 31): Decimal("1.10")}},
        fx_rates={date(2025, 1, 31): Decimal("1.30")},
        previous_eod_by_security={},
    )

    row = position_response_row(
        portfolio_id="P1",
        row=_position_row(valuation_date=date(2025, 1, 31)),
        portfolio_currency="USD",
        reporting_currency="SGD",
        dimensions=["asset_class", "sector"],
        include_cash_flows=True,
        support_inputs=support_inputs,
        previous_eod_by_security={},
    )

    assert row.position_id == "P1:SEC_A"
    assert row.position_to_portfolio_fx_rate == Decimal("1.10")
    assert row.portfolio_to_reporting_fx_rate == Decimal("1.30")
    assert row.beginning_market_value_portfolio_currency == Decimal("110.00")
    assert row.beginning_market_value_reporting_currency == Decimal("143.0000")
    assert row.dimensions == {"asset_class": "Equity", "sector": "Technology"}


def test_position_response_rows_carries_previous_eod_between_valuation_dates() -> None:
    support_inputs = SimpleNamespace(
        position_cashflows_by_key={},
        portfolio_cashflows_by_date={},
        position_to_portfolio_rates={},
        fx_rates={},
        previous_eod_by_security={},
    )

    rows, quality_distribution = position_response_rows(
        portfolio_id="P1",
        rows_page=[
            _position_row(
                valuation_date=date(2025, 1, 30),
                bod_market_value=Decimal("0"),
                eod_market_value=Decimal("110"),
            ),
            _position_row(
                valuation_date=date(2025, 1, 31),
                bod_market_value=Decimal("0"),
                eod_market_value=Decimal("120"),
                epoch=1,
            ),
        ],
        portfolio_currency="EUR",
        reporting_currency="EUR",
        dimensions=[],
        include_cash_flows=True,
        support_inputs=support_inputs,
    )

    assert rows[0].beginning_market_value_position_currency == Decimal("0")
    assert rows[1].beginning_market_value_position_currency == Decimal("110")
    assert quality_distribution == {"final": 1, "restated": 1}


def test_position_response_row_omits_cash_flows_when_not_requested() -> None:
    cash_flow = CashFlowObservation(
        amount=Decimal("10"),
        timing="bod",
        cash_flow_type="external_flow",
        flow_scope="external",
        source_classification="CASHFLOW_IN",
    )
    support_inputs = SimpleNamespace(
        position_cashflows_by_key={("SEC_A", date(2025, 1, 31)): [cash_flow]},
        portfolio_cashflows_by_date={},
        position_to_portfolio_rates={},
        fx_rates={},
        previous_eod_by_security={},
    )

    row = position_response_row(
        portfolio_id="P1",
        row=_position_row(valuation_date=date(2025, 1, 31), position_currency="EUR"),
        portfolio_currency="EUR",
        reporting_currency="EUR",
        dimensions=[],
        include_cash_flows=False,
        support_inputs=support_inputs,
        previous_eod_by_security={},
    )

    assert row.cash_flows == []
