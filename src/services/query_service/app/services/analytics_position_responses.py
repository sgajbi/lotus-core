from __future__ import annotations

from datetime import date
from decimal import Decimal

from ..dtos.analytics_input_dto import PositionTimeseriesRow
from ..repositories.currency_codes import normalize_currency_code
from ..repositories.identifier_normalization import normalize_security_id
from .analytics_cash_flows import effective_beginning_market_value, has_external_flow
from .analytics_fx_rates import portfolio_to_reporting_rate, position_to_portfolio_rate
from .analytics_quality import quality_status_from_epoch
from .decimal_amounts import decimal_or_zero


def position_response_rows(
    *,
    portfolio_id: str,
    rows_page: list[object],
    portfolio_currency: str,
    reporting_currency: str,
    dimensions: list[str],
    include_cash_flows: bool,
    support_inputs: object,
) -> tuple[list[PositionTimeseriesRow], dict[str, int]]:
    quality_distribution: dict[str, int] = {}
    response_rows: list[PositionTimeseriesRow] = []
    previous_eod_by_security = dict(support_inputs.previous_eod_by_security)
    current_valuation_date: date | None = None
    current_eod_by_security: dict[str, Decimal] = {}
    for row in rows_page:
        if current_valuation_date is None:
            current_valuation_date = row.valuation_date
        elif row.valuation_date != current_valuation_date:
            previous_eod_by_security = current_eod_by_security
            current_eod_by_security = {}
            current_valuation_date = row.valuation_date

        response_row = position_response_row(
            portfolio_id=portfolio_id,
            row=row,
            portfolio_currency=portfolio_currency,
            reporting_currency=reporting_currency,
            dimensions=dimensions,
            include_cash_flows=include_cash_flows,
            support_inputs=support_inputs,
            previous_eod_by_security=previous_eod_by_security,
        )
        quality_distribution[response_row.valuation_status] = (
            quality_distribution.get(response_row.valuation_status, 0) + 1
        )
        response_rows.append(response_row)
        current_eod_by_security[response_row.security_id] = (
            response_row.ending_market_value_position_currency
        )
    return response_rows, quality_distribution


def position_response_row(
    *,
    portfolio_id: str,
    row: object,
    portfolio_currency: str,
    reporting_currency: str,
    dimensions: list[str],
    include_cash_flows: bool,
    support_inputs: object,
    previous_eod_by_security: dict[str, Decimal],
) -> PositionTimeseriesRow:
    quality = quality_status_from_epoch(int(row.epoch))
    position_currency = (
        normalize_currency_code(str(row.position_currency))
        if row.position_currency
        else portfolio_currency
    )
    position_to_portfolio_fx_rate = position_to_portfolio_rate(
        position_currency=position_currency,
        portfolio_currency=portfolio_currency,
        valuation_date=row.valuation_date,
        position_to_portfolio_rates=support_inputs.position_to_portfolio_rates,
    )
    portfolio_to_reporting_fx_rate = portfolio_to_reporting_rate(
        portfolio_currency=portfolio_currency,
        reporting_currency=reporting_currency,
        valuation_date=row.valuation_date,
        fx_rates=support_inputs.fx_rates,
    )
    security_id = normalize_security_id(row.security_id)
    cash_flows = (
        support_inputs.position_cashflows_by_key.get((security_id, row.valuation_date), [])
        if include_cash_flows
        else []
    )
    beginning_market_value_position = effective_beginning_market_value(
        row,
        previous_eod_market_value=previous_eod_by_security.get(security_id),
        cash_flows=cash_flows,
        has_portfolio_external_flow=has_external_flow(
            support_inputs.portfolio_cashflows_by_date.get(row.valuation_date, [])
        ),
    )
    ending_market_value_position = decimal_or_zero(row.eod_market_value)
    beginning_market_value_portfolio = (
        beginning_market_value_position * position_to_portfolio_fx_rate
    )
    ending_market_value_portfolio = ending_market_value_position * position_to_portfolio_fx_rate
    return PositionTimeseriesRow(
        position_id=f"{portfolio_id}:{security_id}",
        security_id=security_id,
        valuation_date=row.valuation_date,
        position_currency=position_currency,
        cash_flow_currency=position_currency,
        position_to_portfolio_fx_rate=position_to_portfolio_fx_rate,
        portfolio_to_reporting_fx_rate=portfolio_to_reporting_fx_rate,
        dimensions={dim: getattr(row, dim, None) for dim in dimensions},
        beginning_market_value_position_currency=beginning_market_value_position,
        ending_market_value_position_currency=ending_market_value_position,
        beginning_market_value_portfolio_currency=beginning_market_value_portfolio,
        ending_market_value_portfolio_currency=ending_market_value_portfolio,
        beginning_market_value_reporting_currency=(
            beginning_market_value_portfolio * portfolio_to_reporting_fx_rate
        ),
        ending_market_value_reporting_currency=(
            ending_market_value_portfolio * portfolio_to_reporting_fx_rate
        ),
        valuation_status=quality,
        quantity=decimal_or_zero(row.quantity),
        cash_flows=cash_flows,
    )
