from __future__ import annotations

from decimal import Decimal
from typing import Literal

AnalyticsCashFlowType = Literal[
    "external_flow",
    "internal_trade_flow",
    "income",
    "expense",
    "transfer",
    "other",
]
AnalyticsFlowScope = Literal["external", "internal", "operational"]


def normalize_position_flow_amount(*, amount: Decimal, classification: str) -> Decimal:
    """
    Convert stored cash-movement direction into the position-view flow direction used by
    position-timeseries and analytics payloads.
    """
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
    if classification in {"CASHFLOW_IN", "CASHFLOW_OUT"}:
        return ("external_flow", "external")

    if classification in {
        "INVESTMENT_OUTFLOW",
        "INVESTMENT_INFLOW",
        "FX_BUY",
        "FX_SELL",
        "INTERNAL",
    }:
        return ("internal_trade_flow", "internal")

    if classification == "TRANSFER":
        if is_position_flow and not is_portfolio_flow:
            return ("internal_trade_flow", "internal")
        return ("transfer", "external" if is_portfolio_flow else "internal")

    if classification == "INCOME":
        return ("income", "operational")

    if classification == "EXPENSE":
        return ("expense", "operational")

    return ("other", "operational")
