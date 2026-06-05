from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from portfolio_common.analytics_cashflow_semantics import (
    classify_analytics_cash_flow,
    normalize_position_flow_amount,
)

from ..dtos.analytics_input_dto import CashFlowObservation
from ..repositories.currency_codes import normalize_currency_code
from ..repositories.identifier_normalization import normalize_security_id
from .decimal_amounts import decimal_or_zero


class AnalyticsCashFlowError(RuntimeError):
    pass


def build_cash_flow_observation(
    row: object,
    *,
    amount: Decimal,
) -> CashFlowObservation:
    cash_flow_type, flow_scope = classify_analytics_cash_flow(
        classification=str(row.classification),
        is_position_flow=bool(row.is_position_flow),
        is_portfolio_flow=bool(row.is_portfolio_flow),
    )
    return CashFlowObservation(
        amount=amount,
        timing=str(row.timing).strip().lower(),
        cash_flow_type=cash_flow_type,
        flow_scope=flow_scope,
        source_classification=str(row.classification),
    )


def portfolio_cash_flows_for_dates(
    cashflow_rows: list[object],
    *,
    reporting_currency: str,
    portfolio_currency: str,
    fx_rates: dict[date, Decimal],
) -> dict[date, list[CashFlowObservation]]:
    normalized_reporting_currency = normalize_currency_code(reporting_currency)
    normalized_portfolio_currency = normalize_currency_code(portfolio_currency)
    flows_by_date: dict[date, list[CashFlowObservation]] = defaultdict(list)
    for row in cashflow_rows:
        conversion_rate = Decimal("1")
        if normalized_reporting_currency != normalized_portfolio_currency:
            valuation_date = row.valuation_date
            if valuation_date not in fx_rates:
                raise AnalyticsCashFlowError(
                    "Missing FX rate for "
                    f"{normalized_portfolio_currency}/{normalized_reporting_currency} "
                    f"on {valuation_date}."
                )
            conversion_rate = fx_rates[valuation_date]
        flows_by_date[row.valuation_date].append(
            build_cash_flow_observation(
                row,
                amount=decimal_or_zero(row.amount) * conversion_rate,
            )
        )
    return flows_by_date


def position_cash_flows_for_keys(
    cashflow_rows: list[object],
) -> dict[tuple[str, date], list[CashFlowObservation]]:
    flows_by_key: dict[tuple[str, date], list[CashFlowObservation]] = defaultdict(list)
    for row in cashflow_rows:
        amount = decimal_or_zero(row.amount)
        if bool(row.is_position_flow):
            amount = normalize_position_flow_amount(
                amount=amount,
                classification=str(row.classification),
            )
        flows_by_key[(normalize_security_id(row.security_id), row.valuation_date)].append(
            build_cash_flow_observation(row, amount=amount)
        )
    return flows_by_key


def has_external_flow(cash_flows: list[CashFlowObservation]) -> bool:
    return any(flow.flow_scope == "external" for flow in cash_flows)


def has_only_internal_flows(cash_flows: list[CashFlowObservation]) -> bool:
    return bool(cash_flows) and all(flow.flow_scope == "internal" for flow in cash_flows)


def effective_beginning_market_value(
    row: object,
    *,
    previous_eod_market_value: Decimal | None,
    cash_flows: list[CashFlowObservation],
    has_portfolio_external_flow: bool,
) -> Decimal:
    stored_beginning = decimal_or_zero(row.bod_market_value)
    ending = decimal_or_zero(row.eod_market_value)
    bod_position_flow = decimal_or_zero(getattr(row, "bod_cashflow_position", 0))

    if has_prior_eod_continuity(
        previous_eod_market_value=previous_eod_market_value,
        bod_position_flow=bod_position_flow,
    ):
        return previous_eod_market_value

    has_internal_position_flow = has_only_internal_flows(cash_flows)
    if is_internal_cash_book_settlement(
        row=row,
        has_portfolio_external_flow=has_portfolio_external_flow,
        has_internal_position_flow=has_internal_position_flow,
    ):
        return ending

    if can_repair_beginning_from_previous_eod(
        previous_eod_market_value=previous_eod_market_value,
        stored_beginning=stored_beginning,
        bod_position_flow=bod_position_flow,
        has_portfolio_external_flow=has_portfolio_external_flow,
        has_internal_position_flow=has_internal_position_flow,
    ):
        return previous_eod_market_value + bod_position_flow

    if is_new_internally_funded_position(
        previous_eod_market_value=previous_eod_market_value,
        ending=ending,
        has_portfolio_external_flow=has_portfolio_external_flow,
        has_internal_position_flow=has_internal_position_flow,
    ):
        return ending

    return stored_beginning


def is_cash_book_position(row: object) -> bool:
    asset_class = str(getattr(row, "asset_class", "") or "").strip().casefold()
    security_id = str(getattr(row, "security_id", "") or "").strip().upper()
    return asset_class == "cash" or security_id.startswith("CASH_")


def has_prior_eod_continuity(
    *,
    previous_eod_market_value: Decimal | None,
    bod_position_flow: Decimal,
) -> bool:
    return (
        previous_eod_market_value is not None
        and previous_eod_market_value != 0
        and bod_position_flow == 0
    )


def is_internal_cash_book_settlement(
    *,
    row: object,
    has_portfolio_external_flow: bool,
    has_internal_position_flow: bool,
) -> bool:
    return (
        is_cash_book_position(row)
        and not has_portfolio_external_flow
        and has_internal_position_flow
    )


def can_repair_beginning_from_previous_eod(
    *,
    previous_eod_market_value: Decimal | None,
    stored_beginning: Decimal,
    bod_position_flow: Decimal,
    has_portfolio_external_flow: bool,
    has_internal_position_flow: bool,
) -> bool:
    return (
        previous_eod_market_value is not None
        and stored_beginning == 0
        and bod_position_flow != 0
        and not has_portfolio_external_flow
        and has_internal_position_flow
    )


def is_new_internally_funded_position(
    *,
    previous_eod_market_value: Decimal | None,
    ending: Decimal,
    has_portfolio_external_flow: bool,
    has_internal_position_flow: bool,
) -> bool:
    no_prior_capital = previous_eod_market_value is None or previous_eod_market_value == 0
    return (
        no_prior_capital
        and ending != 0
        and (not has_portfolio_external_flow and has_internal_position_flow)
    )
