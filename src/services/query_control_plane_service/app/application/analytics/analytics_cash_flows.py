"""Cashflow normalization and allocation policies for analytics source observations."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from portfolio_common.domain.analytics.cashflow_semantics import (
    classify_analytics_cash_flow,
    normalize_position_flow_amount,
)
from portfolio_common.domain.currency import normalize_currency_code
from portfolio_common.domain.decimal_amount import decimal_or_zero
from portfolio_common.domain.instrument_classification import is_cash_instrument
from portfolio_common.identifiers import normalize_lookup_identifier as normalize_security_id

from ...contracts.analytics_inputs import CashFlowObservation
from ...domain.analytics import AnalyticsCashflowEvidence, PositionValuationObservation
from .analytics_fx_rates import (
    AnalyticsFxRateError,
    portfolio_to_reporting_rate,
    position_to_portfolio_rate,
)


class AnalyticsCashFlowError(RuntimeError):
    pass


def build_cash_flow_observation(
    row: AnalyticsCashflowEvidence,
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
    cashflow_rows: list[AnalyticsCashflowEvidence],
    *,
    reporting_currency: str,
    portfolio_currency: str,
    cashflow_to_portfolio_rates: dict[str, dict[date, Decimal]],
    portfolio_to_reporting_rates: dict[date, Decimal],
) -> dict[date, list[CashFlowObservation]]:
    normalized_reporting_currency = normalize_currency_code(reporting_currency)
    normalized_portfolio_currency = normalize_currency_code(portfolio_currency)
    flows_by_date: dict[date, list[CashFlowObservation]] = defaultdict(list)
    for row in cashflow_rows:
        try:
            cashflow_currency = normalize_currency_code(row.currency)
        except ValueError as exc:
            raise AnalyticsCashFlowError(
                f"Invalid source currency for cashflow transaction {row.transaction_id}."
            ) from exc
        try:
            conversion_rate = position_to_portfolio_rate(
                position_currency=cashflow_currency,
                portfolio_currency=normalized_portfolio_currency,
                valuation_date=row.valuation_date,
                position_to_portfolio_rates=cashflow_to_portfolio_rates,
            ) * portfolio_to_reporting_rate(
                portfolio_currency=normalized_portfolio_currency,
                reporting_currency=normalized_reporting_currency,
                valuation_date=row.valuation_date,
                fx_rates=portfolio_to_reporting_rates,
            )
        except AnalyticsFxRateError as exc:
            raise AnalyticsCashFlowError(str(exc)) from exc
        flows_by_date[row.valuation_date].append(
            build_cash_flow_observation(
                row,
                amount=decimal_or_zero(row.amount) * conversion_rate,
            )
        )
    return flows_by_date


def position_cash_flows_for_keys(
    cashflow_rows: list[AnalyticsCashflowEvidence],
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
    row: PositionValuationObservation,
    *,
    previous_eod_market_value: Decimal | None,
    cash_flows: list[CashFlowObservation],
    has_portfolio_external_flow: bool,
) -> Decimal:
    stored_beginning: Decimal = decimal_or_zero(row.bod_market_value)
    ending: Decimal = decimal_or_zero(row.eod_market_value)
    bod_position_flow: Decimal = decimal_or_zero(getattr(row, "bod_cashflow_position", 0))

    if previous_eod_market_value is not None and has_prior_eod_continuity(
        previous_eod_market_value=previous_eod_market_value,
        bod_position_flow=bod_position_flow,
    ):
        return previous_eod_market_value

    has_internal_position_flow = has_only_internal_flows(cash_flows)
    if has_sourced_zero_open_for_internal_acquisition(
        stored_beginning=stored_beginning,
        previous_eod_market_value=previous_eod_market_value,
        bod_position_flow=bod_position_flow,
        cash_flows=cash_flows,
        ending=ending,
        has_portfolio_external_flow=has_portfolio_external_flow,
        has_internal_position_flow=has_internal_position_flow,
    ):
        return stored_beginning

    if has_authoritative_internal_cash_open(
        row=row,
        stored_beginning=stored_beginning,
        previous_eod_market_value=previous_eod_market_value,
        has_portfolio_external_flow=has_portfolio_external_flow,
        has_internal_position_flow=has_internal_position_flow,
    ):
        return stored_beginning

    if has_sourced_zero_open_for_first_day_cash_settlement(
        row=row,
        stored_beginning=stored_beginning,
        previous_eod_market_value=previous_eod_market_value,
        bod_position_flow=bod_position_flow,
        cash_flows=cash_flows,
        ending=ending,
        has_portfolio_external_flow=has_portfolio_external_flow,
        has_internal_position_flow=has_internal_position_flow,
    ):
        return stored_beginning

    if is_internal_cash_book_settlement(
        row=row,
        has_portfolio_external_flow=has_portfolio_external_flow,
        has_internal_position_flow=has_internal_position_flow,
    ):
        return ending

    if previous_eod_market_value is not None and can_repair_beginning_from_previous_eod(
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


def is_cash_book_position(row: PositionValuationObservation) -> bool:
    return bool(
        is_cash_instrument(
            product_type=getattr(row, "product_type", None),
            asset_class=getattr(row, "asset_class", None),
        )
    )


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


def has_authoritative_internal_cash_open(
    *,
    row: PositionValuationObservation,
    stored_beginning: Decimal,
    previous_eod_market_value: Decimal | None,
    has_portfolio_external_flow: bool,
    has_internal_position_flow: bool,
) -> bool:
    """Keep a sourced cash opening when it reconciles to the prior close.

    A same-day BOD receipt is already in the closing cash balance. Replacing
    this independently corroborated opening with that close erases income from
    portfolio return and creates a negative cash-sleeve return. A missing or
    contradictory opening still follows the existing conservative fallback.
    """
    return bool(
        is_cash_book_position(row)
        and has_internal_position_flow
        and not has_portfolio_external_flow
        and previous_eod_market_value is not None
        and stored_beginning == previous_eod_market_value
    )


def has_sourced_zero_open_for_internal_acquisition(
    *,
    stored_beginning: Decimal,
    previous_eod_market_value: Decimal | None,
    bod_position_flow: Decimal,
    cash_flows: list[CashFlowObservation],
    ending: Decimal,
    has_portfolio_external_flow: bool,
    has_internal_position_flow: bool,
) -> bool:
    """Do not preload a newly bought position into portfolio opening capital.

    The durable zero opening and absent prior holding agree; the sourced BOD
    internal flow supplies acquisition capital. For a trade whose cashflow is
    settlement-dated, the snapshot BOD-flow column may still be zero; the
    normalized trade-date position flow is the corroborating evidence. Using
    today's EOD or the flow amount as opening capital double-counts the purchase.
    """
    return bool(
        stored_beginning == 0
        and previous_eod_market_value in (None, Decimal("0"))
        and (
            bod_position_flow > 0
            or any(
                flow.amount > 0
                and flow.timing == "bod"
                and flow.flow_scope == "internal"
                and flow.cash_flow_type == "internal_trade_flow"
                and flow.source_classification == "INVESTMENT_OUTFLOW"
                for flow in cash_flows
            )
        )
        and ending > 0
        and has_internal_position_flow
        and not has_portfolio_external_flow
    )


def is_internal_cash_book_settlement(
    *,
    row: PositionValuationObservation,
    has_portfolio_external_flow: bool,
    has_internal_position_flow: bool,
) -> bool:
    return (
        is_cash_book_position(row)
        and not has_portfolio_external_flow
        and has_internal_position_flow
    )


def has_sourced_zero_open_for_first_day_cash_settlement(
    *,
    row: PositionValuationObservation,
    stored_beginning: Decimal,
    previous_eod_market_value: Decimal | None,
    bod_position_flow: Decimal,
    cash_flows: list[CashFlowObservation],
    ending: Decimal,
    has_portfolio_external_flow: bool,
    has_internal_position_flow: bool,
) -> bool:
    """Keep zero opening when an EOD internal transfer fully explains new cash.

    A first-day cash leg of a paired purchase has no prior capital. Preloading
    its negative EOD balance into BOD would break the paired position opening;
    only exact source-flow reconciliation permits the zero to survive.
    """
    return bool(
        is_cash_book_position(row)
        and stored_beginning == 0
        and previous_eod_market_value in (None, Decimal("0"))
        and bod_position_flow == 0
        and ending != 0
        and has_internal_position_flow
        and not has_portfolio_external_flow
        and all(
            flow.timing == "eod"
            and flow.cash_flow_type == "internal_trade_flow"
            and flow.source_classification == "TRANSFER"
            for flow in cash_flows
        )
        and sum((flow.amount for flow in cash_flows), Decimal("0")) == ending
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
