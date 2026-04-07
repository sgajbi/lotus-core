"""Automated lotus-core demo data pack ingest + verification."""

from __future__ import annotations

import argparse
import json
import logging
import math
import time
from dataclasses import dataclass
from decimal import Decimal
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib import error, parse, request

LOGGER = logging.getLogger("demo_data_pack")

DEFAULT_DEMO_BENCHMARK_ID = "BMK_GLOBAL_BALANCED_60_40"
DEFAULT_DEMO_BENCHMARK_PORTFOLIO_ID = "DEMO_ADV_USD_001"


@dataclass(frozen=True)
class PortfolioExpectation:
    portfolio_id: str
    min_positions: int
    min_valued_positions: int
    min_transactions: int
    expected_terminal_quantities: tuple[tuple[str, float], ...]


DEMO_EXPECTATIONS: tuple[PortfolioExpectation, ...] = (
    PortfolioExpectation(
        "DEMO_ADV_USD_001",
        1,
        1,
        8,
        (("CASH_USD", 235350.0), ("SEC_AAPL_US", 800.0), ("SEC_UST_5Y", 120.0)),
    ),
    PortfolioExpectation(
        "DEMO_DPM_EUR_001",
        1,
        1,
        7,
        (("CASH_EUR", 372400.0), ("SEC_SAP_DE", 1200.0), ("SEC_ETF_WORLD_USD", 1000.0)),
    ),
    PortfolioExpectation(
        "DEMO_INCOME_CHF_001",
        1,
        1,
        7,
        (("CASH_CHF", 246580.0), ("SEC_NOVN_CH", 1000.0), ("SEC_CORP_IG_USD", 90.0)),
    ),
    PortfolioExpectation(
        "DEMO_BALANCED_SGD_001",
        1,
        1,
        7,
        (("CASH_SGD", 542500.0), ("SEC_SONY_JP", -200.0), ("SEC_GOLD_ETC_USD", 500.0)),
    ),
    PortfolioExpectation(
        "DEMO_REBAL_USD_001",
        1,
        1,
        8,
        (("CASH_USD", 125480.0), ("SEC_FUND_EM_EQ", 1800.0), ("SEC_CORP_IG_USD", 60.0)),
    ),
)


def _business_dates(start: date, end: date) -> list[str]:
    dates: list[str] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            dates.append(current.isoformat())
        current += timedelta(days=1)
    return dates


def _calendar_dates(start: date, end: date) -> list[str]:
    dates: list[str] = []
    current = start
    while current <= end:
        dates.append(current.isoformat())
        current += timedelta(days=1)
    return dates


def _tx(
    tx_id: str,
    portfolio_id: str,
    instrument_id: str,
    security_id: str,
    when: str,
    tx_type: str,
    qty: float,
    px: float,
    gross: float,
    ccy: str,
) -> dict[str, Any]:
    return {
        "transaction_id": tx_id,
        "portfolio_id": portfolio_id,
        "instrument_id": instrument_id,
        "security_id": security_id,
        "transaction_date": when,
        "transaction_type": tx_type,
        "quantity": qty,
        "price": px,
        "gross_transaction_amount": gross,
        "trade_currency": ccy,
        "currency": ccy,
    }


def _iso_utc_timestamp(day: date, hour: int = 21) -> str:
    return (
        datetime(day.year, day.month, day.day, hour=hour, tzinfo=UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _build_index_series(
    *,
    dates: list[str],
    index_id: str,
    series_id_prefix: str,
    start_level: float,
    drift: float,
    primary_amplitude: float,
    primary_cycle: float,
    secondary_amplitude: float,
    secondary_cycle: float,
    currency: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[Decimal]]:
    index_prices: list[dict[str, Any]] = []
    index_returns: list[dict[str, Any]] = []
    daily_returns: list[Decimal] = []
    current_level = start_level

    for index, current_date in enumerate(dates):
        if index == 0:
            daily_return = 0.0
        else:
            daily_return = (
                drift
                + primary_amplitude * math.sin(index / primary_cycle)
                + secondary_amplitude * math.cos(index / secondary_cycle)
            )
        daily_return_decimal = Decimal(f"{daily_return:.10f}")
        current_level *= 1 + daily_return
        daily_returns.append(daily_return_decimal)
        source_timestamp = _iso_utc_timestamp(date.fromisoformat(current_date))
        index_prices.append(
            {
                "series_id": f"{series_id_prefix}_price",
                "index_id": index_id,
                "series_date": current_date,
                "index_price": f"{current_level:.10f}",
                "series_currency": currency,
                "value_convention": "close_price",
                "source_timestamp": source_timestamp,
                "source_vendor": "LOTUS_DEMO",
                "source_record_id": f"{series_id_prefix}_price_{current_date}",
                "quality_status": "accepted",
            }
        )
        index_returns.append(
            {
                "series_id": f"{series_id_prefix}_return",
                "index_id": index_id,
                "series_date": current_date,
                "index_return": f"{daily_return_decimal:.10f}",
                "return_period": "1d",
                "return_convention": "total_return_index",
                "series_currency": currency,
                "source_timestamp": source_timestamp,
                "source_vendor": "LOTUS_DEMO",
                "source_record_id": f"{series_id_prefix}_return_{current_date}",
                "quality_status": "accepted",
            }
        )

    return index_prices, index_returns, daily_returns


def _build_benchmark_reference_data(*, dates: list[str], start_date: date) -> dict[str, Any]:
    effective_from = start_date.isoformat()
    latest_date = dates[-1]
    series_dates = _calendar_dates(start_date - timedelta(days=1), date.fromisoformat(latest_date))

    equity_prices, equity_returns, equity_daily_returns = _build_index_series(
        dates=series_dates,
        index_id="IDX_GLOBAL_EQUITY_TR",
        series_id_prefix="idx_global_equity_tr",
        start_level=100.0,
        drift=0.00058,
        primary_amplitude=0.00135,
        primary_cycle=14.0,
        secondary_amplitude=-0.00042,
        secondary_cycle=7.5,
        currency="USD",
    )
    bond_prices, bond_returns, bond_daily_returns = _build_index_series(
        dates=series_dates,
        index_id="IDX_GLOBAL_BOND_TR",
        series_id_prefix="idx_global_bond_tr",
        start_level=100.0,
        drift=0.00016,
        primary_amplitude=0.00028,
        primary_cycle=16.0,
        secondary_amplitude=-0.00011,
        secondary_cycle=9.0,
        currency="USD",
    )

    benchmark_return_series: list[dict[str, Any]] = []
    for current_date, equity_return, bond_return in zip(
        series_dates, equity_daily_returns, bond_daily_returns, strict=True
    ):
        benchmark_return = (equity_return * Decimal("0.6")) + (
            bond_return * Decimal("0.4")
        )
        benchmark_return_series.append(
            {
                "series_id": "bmk_global_balanced_60_40_return",
                "benchmark_id": DEFAULT_DEMO_BENCHMARK_ID,
                "series_date": current_date,
                "benchmark_return": f"{benchmark_return:.10f}",
                "return_period": "1d",
                "return_convention": "total_return_index",
                "series_currency": "USD",
                "source_timestamp": _iso_utc_timestamp(date.fromisoformat(current_date)),
                "source_vendor": "LOTUS_DEMO",
                "source_record_id": f"bmk_global_balanced_60_40_return_{current_date}",
                "quality_status": "accepted",
            }
        )

    return {
        "benchmark_assignments": [
            {
                "portfolio_id": DEFAULT_DEMO_BENCHMARK_PORTFOLIO_ID,
                "benchmark_id": DEFAULT_DEMO_BENCHMARK_ID,
                "effective_from": effective_from,
                "assignment_source": "lotus_core_demo_pack",
                "assignment_status": "active",
                "policy_pack_id": "demo_balanced_policy_v1",
                "source_system": "LOTUS_CORE_DEMO_DATA_PACK",
                "assignment_recorded_at": _iso_utc_timestamp(start_date, hour=8),
                "assignment_version": 1,
            }
        ],
        "benchmark_definitions": [
            {
                "benchmark_id": DEFAULT_DEMO_BENCHMARK_ID,
                "benchmark_name": "Global Balanced 60/40",
                "benchmark_type": "composite",
                "benchmark_currency": "USD",
                "return_convention": "total_return_index",
                "benchmark_status": "active",
                "benchmark_family": "multi_asset_strategic",
                "benchmark_provider": "LOTUS_DEMO",
                "rebalance_frequency": "monthly",
                "classification_set_id": "wm_global_taxonomy_v1",
                "classification_labels": {
                    "asset_class": "multi_asset",
                    "strategy": "balanced",
                    "region": "global",
                },
                "effective_from": effective_from,
                "source_timestamp": _iso_utc_timestamp(start_date),
                "source_vendor": "LOTUS_DEMO",
                "source_record_id": "bmk_global_balanced_60_40_definition",
            }
        ],
        "benchmark_compositions": [
            {
                "benchmark_id": DEFAULT_DEMO_BENCHMARK_ID,
                "index_id": "IDX_GLOBAL_EQUITY_TR",
                "composition_effective_from": effective_from,
                "composition_weight": "0.6000000000",
                "rebalance_event_id": "bmk_global_balanced_60_40_initial",
                "source_timestamp": _iso_utc_timestamp(start_date),
                "source_vendor": "LOTUS_DEMO",
                "source_record_id": "bmk_global_balanced_60_40_equity",
                "quality_status": "accepted",
            },
            {
                "benchmark_id": DEFAULT_DEMO_BENCHMARK_ID,
                "index_id": "IDX_GLOBAL_BOND_TR",
                "composition_effective_from": effective_from,
                "composition_weight": "0.4000000000",
                "rebalance_event_id": "bmk_global_balanced_60_40_initial",
                "source_timestamp": _iso_utc_timestamp(start_date),
                "source_vendor": "LOTUS_DEMO",
                "source_record_id": "bmk_global_balanced_60_40_bond",
                "quality_status": "accepted",
            },
        ],
        "indices": [
            {
                "index_id": "IDX_GLOBAL_EQUITY_TR",
                "index_name": "Global Equity Total Return",
                "index_currency": "USD",
                "index_type": "equity_index",
                "index_status": "active",
                "index_provider": "LOTUS_DEMO",
                "index_market": "global_equity",
                "classification_set_id": "wm_global_taxonomy_v1",
                "classification_labels": {
                    "asset_class": "equity",
                    "region": "global",
                },
                "effective_from": effective_from,
                "source_timestamp": _iso_utc_timestamp(start_date),
                "source_vendor": "LOTUS_DEMO",
                "source_record_id": "idx_global_equity_tr_definition",
            },
            {
                "index_id": "IDX_GLOBAL_BOND_TR",
                "index_name": "Global Bond Total Return",
                "index_currency": "USD",
                "index_type": "bond_index",
                "index_status": "active",
                "index_provider": "LOTUS_DEMO",
                "index_market": "global_bond",
                "classification_set_id": "wm_global_taxonomy_v1",
                "classification_labels": {
                    "asset_class": "fixed_income",
                    "region": "global",
                },
                "effective_from": effective_from,
                "source_timestamp": _iso_utc_timestamp(start_date),
                "source_vendor": "LOTUS_DEMO",
                "source_record_id": "idx_global_bond_tr_definition",
            },
        ],
        "index_price_series": [*equity_prices, *bond_prices],
        "index_return_series": [*equity_returns, *bond_returns],
        "benchmark_return_series": benchmark_return_series,
        "benchmark_verification": {
            "portfolio_id": DEFAULT_DEMO_BENCHMARK_PORTFOLIO_ID,
            "benchmark_id": DEFAULT_DEMO_BENCHMARK_ID,
            "start_date": effective_from,
            "end_date": latest_date,
        },
    }


def build_risk_free_reference_data(
    *,
    start_date: date,
    end_date: date,
    currency: str = "USD",
    curve_id: str | None = None,
    annualized_rate: Decimal = Decimal("0.0435000000"),
    source_vendor: str = "LOTUS_DEMO",
    source_prefix: str = "risk_free",
) -> dict[str, Any]:
    normalized_currency = currency.upper()
    normalized_curve_id = curve_id or f"{normalized_currency}_SOFR_3M"
    risk_free_series: list[dict[str, Any]] = []
    for current_date in _calendar_dates(start_date, end_date):
        risk_free_series.append(
            {
                "series_id": f"{source_prefix}_{normalized_currency.lower()}_annualized_rate",
                "risk_free_curve_id": normalized_curve_id,
                "series_date": current_date,
                "value": f"{annualized_rate:.10f}",
                "value_convention": "annualized_rate",
                "day_count_convention": "ACT_360",
                "compounding_convention": "simple",
                "series_currency": normalized_currency,
                "source_timestamp": _iso_utc_timestamp(date.fromisoformat(current_date)),
                "source_vendor": source_vendor,
                "source_record_id": f"{source_prefix}_{normalized_currency.lower()}_{current_date}",
                "quality_status": "accepted",
            }
        )
    return {"risk_free_series": risk_free_series}


def build_demo_bundle() -> dict[str, Any]:
    start_date = date.today() - timedelta(days=365)
    end_date = date.today()
    dates = _business_dates(start_date, end_date)
    as_of = end_date.isoformat()
    tx_anchor = date.fromisoformat(dates[0]) if dates else start_date

    def tx_ts(day_offset: int, hour: int = 10) -> str:
        stamp = datetime(
            year=(tx_anchor + timedelta(days=day_offset)).year,
            month=(tx_anchor + timedelta(days=day_offset)).month,
            day=(tx_anchor + timedelta(days=day_offset)).day,
            hour=hour,
            minute=0,
            second=0,
            tzinfo=UTC,
        )
        return stamp.isoformat().replace("+00:00", "Z")
    portfolios = [
        {
            "portfolio_id": "DEMO_ADV_USD_001",
            "base_currency": "USD",
            "open_date": "2024-01-02",
            "risk_exposure": "Moderate",
            "investment_time_horizon": "Long",
            "portfolio_type": "Advisory",
            "booking_center_code": "Singapore",
            "client_id": "DEMO_CIF_100",
            "status": "ACTIVE",
            "cost_basis_method": "FIFO",
        },
        {
            "portfolio_id": "DEMO_DPM_EUR_001",
            "base_currency": "EUR",
            "open_date": "2024-01-02",
            "risk_exposure": "Balanced",
            "investment_time_horizon": "Long",
            "portfolio_type": "Discretionary",
            "booking_center_code": "Zurich",
            "client_id": "DEMO_CIF_200",
            "status": "ACTIVE",
            "cost_basis_method": "FIFO",
        },
        {
            "portfolio_id": "DEMO_INCOME_CHF_001",
            "base_currency": "CHF",
            "open_date": "2024-01-02",
            "risk_exposure": "Low",
            "investment_time_horizon": "Medium",
            "portfolio_type": "Advisory",
            "booking_center_code": "Zurich",
            "client_id": "DEMO_CIF_300",
            "status": "ACTIVE",
            "cost_basis_method": "AVCO",
        },
        {
            "portfolio_id": "DEMO_BALANCED_SGD_001",
            "base_currency": "SGD",
            "open_date": "2024-01-02",
            "risk_exposure": "Balanced",
            "investment_time_horizon": "Long",
            "portfolio_type": "Discretionary",
            "booking_center_code": "Singapore",
            "client_id": "DEMO_CIF_400",
            "status": "ACTIVE",
            "cost_basis_method": "FIFO",
        },
        {
            "portfolio_id": "DEMO_REBAL_USD_001",
            "base_currency": "USD",
            "open_date": "2024-01-02",
            "risk_exposure": "Moderate",
            "investment_time_horizon": "Medium",
            "portfolio_type": "Advisory",
            "booking_center_code": "New York",
            "client_id": "DEMO_CIF_500",
            "status": "ACTIVE",
            "cost_basis_method": "FIFO",
        },
    ]
    instruments = [
        {"security_id": "CASH_USD", "name": "US Dollar Cash", "isin": "CASH_USD_DEMO", "currency": "USD", "product_type": "Cash", "asset_class": "Cash"},
        {"security_id": "CASH_EUR", "name": "Euro Cash", "isin": "CASH_EUR_DEMO", "currency": "EUR", "product_type": "Cash", "asset_class": "Cash"},
        {"security_id": "CASH_CHF", "name": "Swiss Franc Cash", "isin": "CASH_CHF_DEMO", "currency": "CHF", "product_type": "Cash", "asset_class": "Cash"},
        {"security_id": "CASH_SGD", "name": "Singapore Dollar Cash", "isin": "CASH_SGD_DEMO", "currency": "SGD", "product_type": "Cash", "asset_class": "Cash"},
        {"security_id": "SEC_AAPL_US", "name": "Apple Inc.", "isin": "US0378331005", "currency": "USD", "product_type": "Equity", "asset_class": "Equity", "sector": "Technology", "country_of_risk": "US"},
        {"security_id": "SEC_SAP_DE", "name": "SAP SE", "isin": "DE0007164600", "currency": "EUR", "product_type": "Equity", "asset_class": "Equity", "sector": "Technology", "country_of_risk": "DE"},
        {"security_id": "SEC_NOVN_CH", "name": "Novartis AG", "isin": "CH0012005267", "currency": "CHF", "product_type": "Equity", "asset_class": "Equity", "sector": "Healthcare", "country_of_risk": "CH"},
        {"security_id": "SEC_SONY_JP", "name": "Sony Group Corp.", "isin": "JP3435000009", "currency": "JPY", "product_type": "Equity", "asset_class": "Equity", "sector": "Consumer Discretionary", "country_of_risk": "JP"},
        {"security_id": "SEC_UST_5Y", "name": "US Treasury 5Y", "isin": "US91282CGM73", "currency": "USD", "product_type": "Bond", "asset_class": "Fixed Income", "rating": "AA+", "maturity_date": "2029-08-31"},
        {"security_id": "SEC_CORP_IG_USD", "name": "Global Corp 4.2% 2030", "isin": "US0000000001", "currency": "USD", "product_type": "Bond", "asset_class": "Fixed Income", "rating": "A-", "maturity_date": "2030-06-15"},
        {"security_id": "SEC_ETF_WORLD_USD", "name": "Global Equity ETF", "isin": "US0000000002", "currency": "USD", "product_type": "ETF", "asset_class": "Equity"},
        {"security_id": "SEC_FUND_EM_EQ", "name": "Emerging Markets Equity Fund", "isin": "LU0000000003", "currency": "USD", "product_type": "Fund", "asset_class": "Equity"},
        {"security_id": "SEC_GOLD_ETC_USD", "name": "Gold ETC", "isin": "JE00B1VS3770", "currency": "USD", "product_type": "ETC", "asset_class": "Commodity"},
    ]
    txs = [
        _tx("DEMO_ADV_DEP_01", "DEMO_ADV_USD_001", "CASH", "CASH_USD", tx_ts(1, 9), "DEPOSIT", 500000, 1, 500000, "USD"),
        _tx("DEMO_ADV_BUY_AAPL_01", "DEMO_ADV_USD_001", "AAPL", "SEC_AAPL_US", tx_ts(2), "BUY", 800, 185, 148000, "USD"),
        _tx("DEMO_ADV_CASH_OUT_01", "DEMO_ADV_USD_001", "CASH", "CASH_USD", tx_ts(2), "SELL", 148000, 1, 148000, "USD"),
        _tx("DEMO_ADV_BUY_UST_01", "DEMO_ADV_USD_001", "UST5Y", "SEC_UST_5Y", tx_ts(5), "BUY", 120, 980, 117600, "USD"),
        _tx("DEMO_ADV_CASH_OUT_02", "DEMO_ADV_USD_001", "CASH", "CASH_USD", tx_ts(5), "SELL", 117600, 1, 117600, "USD"),
        _tx("DEMO_ADV_DIV_01", "DEMO_ADV_USD_001", "AAPL", "SEC_AAPL_US", tx_ts(160), "DIVIDEND", 0, 0, 1200, "USD"),
        _tx("DEMO_ADV_CASH_IN_01", "DEMO_ADV_USD_001", "CASH", "CASH_USD", tx_ts(160), "BUY", 1200, 1, 1200, "USD"),
        _tx("DEMO_ADV_FEE_01", "DEMO_ADV_USD_001", "CASH", "CASH_USD", tx_ts(330), "FEE", 1, 250, 250, "USD"),
        _tx("DEMO_DPM_DEP_01", "DEMO_DPM_EUR_001", "CASH", "CASH_EUR", tx_ts(1, 9), "DEPOSIT", 600000, 1, 600000, "EUR"),
        _tx("DEMO_DPM_BUY_SAP_01", "DEMO_DPM_EUR_001", "SAP", "SEC_SAP_DE", tx_ts(3), "BUY", 1500, 120, 180000, "EUR"),
        _tx("DEMO_DPM_CASH_OUT_01", "DEMO_DPM_EUR_001", "CASH", "CASH_EUR", tx_ts(3), "SELL", 180000, 1, 180000, "EUR"),
        _tx("DEMO_DPM_BUY_ETF_01", "DEMO_DPM_EUR_001", "WORLD_ETF", "SEC_ETF_WORLD_USD", tx_ts(12), "BUY", 1000, 95, 95000, "USD"),
        _tx("DEMO_DPM_CASH_OUT_02", "DEMO_DPM_EUR_001", "CASH", "CASH_EUR", tx_ts(12), "SELL", 86000, 1, 86000, "EUR"),
        _tx("DEMO_DPM_SELL_SAP_01", "DEMO_DPM_EUR_001", "SAP", "SEC_SAP_DE", tx_ts(220), "SELL", 300, 128, 38400, "EUR"),
        _tx("DEMO_DPM_CASH_IN_01", "DEMO_DPM_EUR_001", "CASH", "CASH_EUR", tx_ts(220), "BUY", 38400, 1, 38400, "EUR"),
        _tx("DEMO_INCOME_DEP_01", "DEMO_INCOME_CHF_001", "CASH", "CASH_CHF", tx_ts(1, 9), "DEPOSIT", 420000, 1, 420000, "CHF"),
        _tx("DEMO_INCOME_BUY_NOVN_01", "DEMO_INCOME_CHF_001", "NOVN", "SEC_NOVN_CH", tx_ts(4), "BUY", 1000, 92, 92000, "CHF"),
        _tx("DEMO_INCOME_CASH_OUT_01", "DEMO_INCOME_CHF_001", "CASH", "CASH_CHF", tx_ts(4), "SELL", 92000, 1, 92000, "CHF"),
        _tx("DEMO_INCOME_BUY_BOND_01", "DEMO_INCOME_CHF_001", "CORP_IG", "SEC_CORP_IG_USD", tx_ts(8), "BUY", 90, 1010, 90900, "USD"),
        _tx("DEMO_INCOME_CASH_OUT_02", "DEMO_INCOME_CHF_001", "CASH", "CASH_CHF", tx_ts(8), "SELL", 82000, 1, 82000, "CHF"),
        _tx("DEMO_INCOME_COUPON_01", "DEMO_INCOME_CHF_001", "CORP_IG", "SEC_CORP_IG_USD", tx_ts(190), "DIVIDEND", 0, 0, 650, "USD"),
        _tx("DEMO_INCOME_CASH_IN_01", "DEMO_INCOME_CHF_001", "CASH", "CASH_CHF", tx_ts(190), "BUY", 580, 1, 580, "CHF"),
        _tx("DEMO_BAL_DEP_01", "DEMO_BALANCED_SGD_001", "CASH", "CASH_SGD", tx_ts(1, 9), "DEPOSIT", 700000, 1, 700000, "SGD"),
        _tx("DEMO_BAL_BUY_SONY_01", "DEMO_BALANCED_SGD_001", "SONY", "SEC_SONY_JP", tx_ts(3), "BUY", 1200, 1750, 2100000, "JPY"),
        _tx("DEMO_BAL_CASH_OUT_01", "DEMO_BALANCED_SGD_001", "CASH", "CASH_SGD", tx_ts(3), "SELL", 19800, 1, 19800, "SGD"),
        _tx("DEMO_BAL_BUY_GOLD_01", "DEMO_BALANCED_SGD_001", "GOLD_ETC", "SEC_GOLD_ETC_USD", tx_ts(30), "BUY", 500, 210, 105000, "USD"),
        _tx("DEMO_BAL_CASH_OUT_02", "DEMO_BALANCED_SGD_001", "CASH", "CASH_SGD", tx_ts(30), "SELL", 141000, 1, 141000, "SGD"),
        _tx("DEMO_BAL_SELL_SONY_01", "DEMO_BALANCED_SGD_001", "SONY", "SEC_SONY_JP", tx_ts(280), "SELL", 200, 1820, 364000, "JPY"),
        _tx("DEMO_BAL_CASH_IN_01", "DEMO_BALANCED_SGD_001", "CASH", "CASH_SGD", tx_ts(280), "BUY", 3300, 1, 3300, "SGD"),
        _tx("DEMO_REBAL_DEP_01", "DEMO_REBAL_USD_001", "CASH", "CASH_USD", tx_ts(1, 9), "DEPOSIT", 300000, 1, 300000, "USD"),
        _tx("DEMO_REBAL_BUY_FUND_01", "DEMO_REBAL_USD_001", "EM_FUND", "SEC_FUND_EM_EQ", tx_ts(10), "BUY", 2000, 55, 110000, "USD"),
        _tx("DEMO_REBAL_CASH_OUT_01", "DEMO_REBAL_USD_001", "CASH", "CASH_USD", tx_ts(10), "SELL", 110000, 1, 110000, "USD"),
        _tx("DEMO_REBAL_BUY_BOND_01", "DEMO_REBAL_USD_001", "CORP_IG", "SEC_CORP_IG_USD", tx_ts(20), "BUY", 60, 1012, 60720, "USD"),
        _tx("DEMO_REBAL_CASH_OUT_02", "DEMO_REBAL_USD_001", "CASH", "CASH_USD", tx_ts(20), "SELL", 60720, 1, 60720, "USD"),
        _tx("DEMO_REBAL_TRANSFER_OUT_01", "DEMO_REBAL_USD_001", "EM_FUND", "SEC_FUND_EM_EQ", tx_ts(240), "TRANSFER_OUT", 200, 56, 11200, "USD"),
        _tx("DEMO_REBAL_CASH_IN_01", "DEMO_REBAL_USD_001", "CASH", "CASH_USD", tx_ts(240), "BUY", 11200, 1, 11200, "USD"),
        _tx("DEMO_REBAL_WITHDRAW_01", "DEMO_REBAL_USD_001", "CASH", "CASH_USD", tx_ts(340), "WITHDRAWAL", 15000, 1, 15000, "USD"),
    ]
    price_paths = {
        "SEC_AAPL_US": (184, 194, "USD"),
        "SEC_SAP_DE": (118, 129, "EUR"),
        "SEC_NOVN_CH": (91, 95, "CHF"),
        "SEC_SONY_JP": (1720, 1835, "JPY"),
        "SEC_UST_5Y": (978, 986, "USD"),
        "SEC_CORP_IG_USD": (1008, 1020, "USD"),
        "SEC_ETF_WORLD_USD": (94, 101, "USD"),
        "SEC_FUND_EM_EQ": (52, 57, "USD"),
        "SEC_GOLD_ETC_USD": (208, 217, "USD"),
    }
    market_prices: list[dict[str, Any]] = []
    for d in dates:
        market_prices.extend(
            [
                {"security_id": "CASH_USD", "price_date": d, "price": 1, "currency": "USD"},
                {"security_id": "CASH_EUR", "price_date": d, "price": 1, "currency": "EUR"},
                {"security_id": "CASH_CHF", "price_date": d, "price": 1, "currency": "CHF"},
                {"security_id": "CASH_SGD", "price_date": d, "price": 1, "currency": "SGD"},
            ]
        )
    for security_id, (start_px, end_px, ccy) in price_paths.items():
        for idx, d in enumerate(dates):
            px = round(start_px + ((end_px - start_px) * idx / (len(dates) - 1)), 2)
            market_prices.append({"security_id": security_id, "price_date": d, "price": px, "currency": ccy})
    fx_paths = {
        ("USD", "EUR"): (0.92, 0.90),
        ("EUR", "USD"): (1.09, 1.11),
        ("USD", "CHF"): (0.88, 0.86),
        ("CHF", "USD"): (1.13, 1.16),
        ("USD", "SGD"): (1.34, 1.32),
        ("SGD", "USD"): (0.75, 0.76),
        ("JPY", "USD"): (0.0069, 0.0067),
        ("JPY", "SGD"): (0.0092, 0.0089),
        ("EUR", "CHF"): (0.96, 0.95),
        ("CHF", "EUR"): (1.04, 1.05),
    }
    fx_rates: list[dict[str, Any]] = []
    for (from_ccy, to_ccy), (start_rate, end_rate) in fx_paths.items():
        for idx, d in enumerate(dates):
            rate = round(start_rate + ((end_rate - start_rate) * idx / (len(dates) - 1)), 6)
            fx_rates.append({"from_currency": from_ccy, "to_currency": to_ccy, "rate_date": d, "rate": rate})
    benchmark_reference = _build_benchmark_reference_data(dates=dates, start_date=start_date)
    risk_free_reference = build_risk_free_reference_data(
        start_date=start_date,
        end_date=end_date,
        currency="USD",
        source_vendor="LOTUS_DEMO",
        source_prefix="demo_risk_free",
    )
    return {
        "source_system": "LOTUS_CORE_DEMO_DATA_PACK",
        "mode": "UPSERT",
        "business_dates": [{"business_date": d} for d in dates],
        "portfolios": portfolios,
        "instruments": instruments,
        "transactions": txs,
        "market_prices": market_prices,
        "fx_rates": fx_rates,
        "as_of_date": as_of,
        **benchmark_reference,
        **risk_free_reference,
    }


def _build_portfolio_bundle_payload(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_system": bundle["source_system"],
        "mode": bundle["mode"],
        "business_dates": bundle["business_dates"],
        "portfolios": bundle["portfolios"],
        "instruments": bundle["instruments"],
        "transactions": bundle["transactions"],
        "market_prices": bundle["market_prices"],
        "fx_rates": bundle["fx_rates"],
        "as_of_date": bundle["as_of_date"],
    }


def _ingest_demo_reference_data(ingestion_base_url: str, bundle: dict[str, Any]) -> None:
    reference_payloads = (
        ("/ingest/indices", {"indices": bundle["indices"]}),
        ("/ingest/index-price-series", {"index_price_series": bundle["index_price_series"]}),
        ("/ingest/index-return-series", {"index_return_series": bundle["index_return_series"]}),
        ("/ingest/benchmark-definitions", {"benchmark_definitions": bundle["benchmark_definitions"]}),
        ("/ingest/benchmark-compositions", {"benchmark_compositions": bundle["benchmark_compositions"]}),
        ("/ingest/benchmark-return-series", {"benchmark_return_series": bundle["benchmark_return_series"]}),
        ("/ingest/benchmark-assignments", {"benchmark_assignments": bundle["benchmark_assignments"]}),
        ("/ingest/risk-free-series", {"risk_free_series": bundle["risk_free_series"]}),
    )
    for endpoint, payload in reference_payloads:
        _request_json("POST", f"{ingestion_base_url}{endpoint}", payload=payload)


def _request_json(method: str, url: str, payload: dict[str, Any] | None = None) -> tuple[int, Any]:
    req = request.Request(
        url=url,
        method=method.upper(),
        data=(None if payload is None else json.dumps(payload).encode("utf-8")),
        headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=15) as response:
            body = response.read().decode("utf-8")
            return response.status, (json.loads(body) if body else {})
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed ({exc.code}): {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"{method} {url} connection error: {exc}") from exc


def _wait_ready(url: str, wait_seconds: int, poll_interval_seconds: int) -> None:
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        try:
            status_code, _ = _request_json("GET", url)
            if status_code == 200:
                return
        except RuntimeError:
            pass
        time.sleep(poll_interval_seconds)
    raise TimeoutError(f"Timed out waiting for readiness endpoint: {url}")


def _portfolio_exists(query_base_url: str, portfolio_id: str) -> bool:
    params = parse.urlencode({"portfolio_id": portfolio_id})
    _, payload = _request_json("GET", f"{query_base_url}/portfolios?{params}")
    return any(item.get("portfolio_id") == portfolio_id for item in payload.get("portfolios") or [])


def _all_demo_portfolios_exist(query_base_url: str) -> bool:
    return all(_portfolio_exists(query_base_url, item.portfolio_id) for item in DEMO_EXPECTATIONS)


def _verify_portfolio(
    query_base_url: str,
    expected: PortfolioExpectation,
    wait_seconds: int,
    poll_interval_seconds: int,
) -> dict[str, Any]:
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        try:
            _, pos_payload = _request_json("GET", f"{query_base_url}/portfolios/{expected.portfolio_id}/positions")
            _, tx_payload = _request_json("GET", f"{query_base_url}/portfolios/{expected.portfolio_id}/transactions?limit=200")
        except RuntimeError:
            time.sleep(poll_interval_seconds)
            continue
        positions = pos_payload.get("positions") or []
        valued = [
            p for p in positions
            if isinstance(p.get("valuation"), dict) and p["valuation"].get("market_value") is not None
        ]
        total_transactions = int(tx_payload.get("total", 0))
        all_quantities_match = True
        for security_id, expected_quantity in expected.expected_terminal_quantities:
            _, history_payload = _request_json(
                "GET",
                f"{query_base_url}/portfolios/{expected.portfolio_id}/position-history?security_id={security_id}",
            )
            history_rows = history_payload.get("positions") or []
            if not history_rows:
                all_quantities_match = False
                break
            latest_row = max(history_rows, key=lambda row: row.get("position_date") or "")
            actual_quantity = float(latest_row.get("quantity", 0.0))
            if abs(actual_quantity - expected_quantity) > 1e-6:
                all_quantities_match = False
                break
        if (
            len(positions) >= expected.min_positions
            and len(valued) >= expected.min_valued_positions
            and total_transactions >= expected.min_transactions
            and all_quantities_match
        ):
            return {
                "portfolio_id": expected.portfolio_id,
                "positions": len(positions),
                "valued_positions": len(valued),
                "transactions": total_transactions,
                "validated_holdings": len(expected.expected_terminal_quantities),
            }
        time.sleep(poll_interval_seconds)
    raise TimeoutError(f"Timed out verifying portfolio outputs for {expected.portfolio_id}.")


def _verify_benchmark_reference(
    query_control_plane_base_url: str,
    *,
    portfolio_id: str,
    benchmark_id: str,
    start_date: str,
    end_date: str,
    wait_seconds: int,
    poll_interval_seconds: int,
) -> dict[str, Any]:
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        try:
            _, catalog_payload = _request_json(
                "POST",
                f"{query_control_plane_base_url}/integration/benchmarks/catalog",
                payload={"as_of_date": end_date},
            )
            _, assignment_payload = _request_json(
                "POST",
                f"{query_control_plane_base_url}/integration/portfolios/{portfolio_id}/benchmark-assignment",
                payload={"as_of_date": end_date},
            )
            _, composition_payload = _request_json(
                "POST",
                f"{query_control_plane_base_url}/integration/benchmarks/{benchmark_id}/composition-window",
                payload={"window": {"start_date": start_date, "end_date": end_date}},
            )
        except RuntimeError:
            time.sleep(poll_interval_seconds)
            continue

        records = catalog_payload.get("records") if isinstance(catalog_payload, dict) else None
        segments = (
            composition_payload.get("segments")
            if isinstance(composition_payload, dict)
            else None
        )
        if (
            isinstance(records, list)
            and any(record.get("benchmark_id") == benchmark_id for record in records)
            and isinstance(assignment_payload, dict)
            and assignment_payload.get("benchmark_id") == benchmark_id
            and isinstance(segments, list)
            and segments
        ):
            return {
                "portfolio_id": portfolio_id,
                "benchmark_id": benchmark_id,
                "catalog_records": len(records),
                "composition_segments": len(segments),
            }
        time.sleep(poll_interval_seconds)
    raise TimeoutError(
        f"Timed out verifying benchmark reference data for {portfolio_id} -> {benchmark_id}."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="lotus-core demo data pack bootstrap")
    parser.add_argument("--ingestion-base-url", default="http://localhost:8200")
    parser.add_argument("--query-base-url", default="http://localhost:8201")
    parser.add_argument("--query-control-plane-base-url", default="http://localhost:8202")
    parser.add_argument("--wait-seconds", type=int, default=300)
    parser.add_argument("--poll-interval-seconds", type=int, default=3)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--ingest-only", action="store_true")
    parser.add_argument("--force-ingest", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))
    ingestion_base_url = args.ingestion_base_url.rstrip("/")
    query_base_url = args.query_base_url.rstrip("/")
    query_control_plane_base_url = args.query_control_plane_base_url.rstrip("/")
    if args.verify_only and args.ingest_only:
        raise ValueError("Cannot use --verify-only with --ingest-only")
    _wait_ready(f"{ingestion_base_url}/health/ready", args.wait_seconds, args.poll_interval_seconds)
    _wait_ready(f"{query_base_url}/health/ready", args.wait_seconds, args.poll_interval_seconds)
    _wait_ready(
        f"{query_control_plane_base_url}/health/ready",
        args.wait_seconds,
        args.poll_interval_seconds,
    )
    demo_bundle = build_demo_bundle()
    if not args.verify_only:
        if args.force_ingest or not _all_demo_portfolios_exist(query_base_url):
            payload = _build_portfolio_bundle_payload(demo_bundle)
            LOGGER.info(
                "Ingesting demo pack: portfolios=%d instruments=%d transactions=%d market_prices=%d fx_rates=%d",
                len(payload["portfolios"]),
                len(payload["instruments"]),
                len(payload["transactions"]),
                len(payload["market_prices"]),
                len(payload["fx_rates"]),
            )
            _request_json("POST", f"{ingestion_base_url}/ingest/portfolio-bundle", payload=payload)
        else:
            LOGGER.info("Demo portfolios already present. Skipping ingestion.")
        _ingest_demo_reference_data(ingestion_base_url, demo_bundle)
        LOGGER.info(
            "Ingested benchmark reference seed: benchmark=%s assigned_portfolio=%s",
            demo_bundle["benchmark_verification"]["benchmark_id"],
            demo_bundle["benchmark_verification"]["portfolio_id"],
        )
    if not args.ingest_only:
        verification_results: list[dict[str, Any]] = []
        for expected in DEMO_EXPECTATIONS:
            result = _verify_portfolio(
                query_base_url,
                expected,
                args.wait_seconds,
                args.poll_interval_seconds,
            )
            verification_results.append(result)
            LOGGER.info(
                "Verified portfolio %s (positions=%d valued_positions=%d transactions=%d holdings_validated=%d)",
                result["portfolio_id"],
                result["positions"],
                result["valued_positions"],
                result["transactions"],
                result["validated_holdings"],
            )
        benchmark_result = _verify_benchmark_reference(
            query_control_plane_base_url,
            portfolio_id=demo_bundle["benchmark_verification"]["portfolio_id"],
            benchmark_id=demo_bundle["benchmark_verification"]["benchmark_id"],
            start_date=demo_bundle["benchmark_verification"]["start_date"],
            end_date=demo_bundle["benchmark_verification"]["end_date"],
            wait_seconds=args.wait_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
        )
        LOGGER.info(
            "Verified benchmark seed %s for %s (catalog_records=%d composition_segments=%d)",
            benchmark_result["benchmark_id"],
            benchmark_result["portfolio_id"],
            benchmark_result["catalog_records"],
            benchmark_result["composition_segments"],
        )
        if len(verification_results) != len(DEMO_EXPECTATIONS):
            raise RuntimeError("Demo verification failed: not all demo portfolios were verified.")
    LOGGER.info("Demo data pack workflow completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
