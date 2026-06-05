from __future__ import annotations

from decimal import Decimal
from typing import Literal

AnalyticsCashFlowType = Literal[
    "external_flow",
    "internal_trade_flow",
    "income",
    "fee",
    "transfer",
    "other",
]
AnalyticsFlowScope = Literal["external", "internal", "operational"]

_STATIC_CASH_FLOW_SEMANTICS: dict[str, tuple[AnalyticsCashFlowType, AnalyticsFlowScope]] = {
    "CASHFLOW_IN": ("external_flow", "external"),
    "CASHFLOW_OUT": ("external_flow", "external"),
    "INVESTMENT_OUTFLOW": ("internal_trade_flow", "internal"),
    "INVESTMENT_INFLOW": ("internal_trade_flow", "internal"),
    "FX_BUY": ("internal_trade_flow", "internal"),
    "FX_SELL": ("internal_trade_flow", "internal"),
    "INTERNAL": ("internal_trade_flow", "internal"),
    "INCOME": ("income", "operational"),
    "EXPENSE": ("fee", "operational"),
}


def normalize_cashflow_timing(timing: str | None) -> str:
    return str(timing or "").strip().upper()


def normalize_position_flow_amount(*, amount: Decimal, classification: str) -> Decimal:
    """
    Convert stored cash-movement direction into the position-view flow direction used by
    position-timeseries and analytics payloads.
    """
    classification = str(classification or "").strip().upper()
    if classification in {"INVESTMENT_OUTFLOW", "INVESTMENT_INFLOW", "INCOME"}:
        return -amount
    return amount


def classify_analytics_cash_flow(
    *,
    classification: str,
    is_position_flow: bool,
    is_portfolio_flow: bool,
) -> tuple[AnalyticsCashFlowType, AnalyticsFlowScope]:
    """
    Map canonical cashflow classifications into analytics-facing semantics.
    """
    classification = str(classification or "").strip().upper()
    if classification == "TRANSFER":
        return _classify_transfer_cash_flow(
            is_position_flow=is_position_flow,
            is_portfolio_flow=is_portfolio_flow,
        )
    return _STATIC_CASH_FLOW_SEMANTICS.get(classification, ("other", "operational"))


def _classify_transfer_cash_flow(
    *,
    is_position_flow: bool,
    is_portfolio_flow: bool,
) -> tuple[AnalyticsCashFlowType, AnalyticsFlowScope]:
    if is_position_flow and not is_portfolio_flow:
        return ("internal_trade_flow", "internal")
    return ("transfer", "external" if is_portfolio_flow else "internal")
