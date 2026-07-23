"""Automated lotus-core demo data pack ingest + verification."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import logging
import math
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from urllib import error, parse, request

from tools.front_office_seed_contract import load_front_office_seed_contract

LOGGER = logging.getLogger("demo_data_pack")

DEFAULT_DEMO_BENCHMARK_ID = "BMK_GLOBAL_BALANCED_60_40"
SECONDARY_DEMO_BENCHMARK_ID = "BMK_GLOBAL_GROWTH_80_20"
DEFAULT_DEMO_BENCHMARK_PORTFOLIO_ID = "DEMO_ADV_USD_001"
MIN_DEMO_HISTORY_DAYS = 240
DEFAULT_DEMO_HISTORY_DAYS = 365 * 3
IDEMPOTENCY_REPLAY_MESSAGE = "Duplicate ingestion request accepted via idempotency replay."

DEMO_SEED_CONTRACT = load_front_office_seed_contract()
DEMO_CANONICAL_AS_OF_DATE = date.fromisoformat(DEMO_SEED_CONTRACT.canonical_as_of_date)
DEMO_BENCHMARK_EFFECTIVE_DATE = date.fromisoformat(DEMO_SEED_CONTRACT.benchmark_start_date)


@dataclass(frozen=True)
class PortfolioExpectation:
    portfolio_id: str
    min_positions: int
    min_valued_positions: int
    min_transactions: int
    expected_terminal_quantities: tuple[tuple[str, float], ...]


@dataclass(frozen=True, slots=True)
class DemoPackIngestionOutcome:
    segment: str
    replayed: bool
    idempotency_key: str | None


@dataclass(frozen=True, slots=True)
class DemoPackSegment:
    name: str
    endpoint: str
    payload: dict[str, Any]
    category: Literal["portfolio", "reference"]

    @property
    def record_count(self) -> int:
        return sum(len(value) for value in self.payload.values() if isinstance(value, list))


@dataclass(frozen=True, slots=True)
class DemoPackCompleteness:
    evaluated_segments: tuple[str, ...]
    missing_segments: tuple[str, ...]

    @property
    def is_complete(self) -> bool:
        return not self.missing_segments


class DemoPackHttpError(RuntimeError):
    def __init__(self, *, method: str, url: str, status_code: int, detail: str) -> None:
        self.status_code = status_code
        super().__init__(f"{method} {url} failed ({status_code}): {detail}")


DEMO_EXPECTATIONS: tuple[PortfolioExpectation, ...] = (
    PortfolioExpectation(
        "DEMO_ADV_USD_001",
        1,
        1,
        15,
        (
            ("CASH_USD", 398905.0),
            ("SEC_AAPL_US", 1420.0),
            ("SEC_UST_5Y", 150.0),
            ("SEC_ETF_WORLD_USD", 530.0),
        ),
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


def _next_business_date(value: date) -> date:
    while value.weekday() >= 5:
        value += timedelta(days=1)
    return value


DEMO_ECONOMIC_ANCHOR_DATE = _next_business_date(
    DEMO_CANONICAL_AS_OF_DATE - timedelta(days=DEFAULT_DEMO_HISTORY_DAYS)
)


def _demo_pack_date_window(history_days: int) -> tuple[date, date]:
    return DEMO_CANONICAL_AS_OF_DATE - timedelta(days=history_days), DEMO_CANONICAL_AS_OF_DATE


def _stable_linear_value(
    *,
    observation_date: date,
    anchor_date: date,
    end_date: date,
    start_value: float,
    end_value: float,
    precision: int,
) -> float:
    span_days = (end_date - anchor_date).days
    if span_days <= 0:
        raise ValueError("Stable value end_date must be after anchor_date.")
    elapsed_days = min(max((observation_date - anchor_date).days, 0), span_days)
    fraction = Decimal(elapsed_days) / Decimal(span_days)
    value = Decimal(str(start_value)) + (
        (Decimal(str(end_value)) - Decimal(str(start_value))) * fraction
    )
    quantum = Decimal(1).scaleb(-precision)
    return float(value.quantize(quantum))


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
        "created_at": when,
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
    economic_anchor: date | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[Decimal]]:
    index_prices: list[dict[str, Any]] = []
    index_returns: list[dict[str, Any]] = []
    daily_returns: list[Decimal] = []
    if not dates:
        return index_prices, index_returns, daily_returns
    parsed_dates = [date.fromisoformat(value) for value in dates]
    if parsed_dates != sorted(parsed_dates):
        raise ValueError("Index series dates must be ordered.")
    anchor = economic_anchor or parsed_dates[0]

    def daily_return_for(observation_date: date) -> float:
        offset = (observation_date - anchor).days
        if offset == 0:
            return 0.0
        return (
            drift
            + primary_amplitude * math.sin(offset / primary_cycle)
            + secondary_amplitude * math.cos(offset / secondary_cycle)
        )

    def level_at(observation_date: date) -> float:
        level = start_level
        current_date = anchor
        while current_date < observation_date:
            current_date += timedelta(days=1)
            level *= 1 + daily_return_for(current_date)
        while current_date > observation_date:
            level /= 1 + daily_return_for(current_date)
            current_date -= timedelta(days=1)
        return level

    current_level = level_at(parsed_dates[0])
    previous_date: date | None = None
    for observation_date in parsed_dates:
        if previous_date is not None:
            cursor = previous_date
            while cursor < observation_date:
                cursor += timedelta(days=1)
                current_level *= 1 + daily_return_for(cursor)
        daily_return = daily_return_for(observation_date)
        if observation_date == anchor:
            daily_return = 0.0
        daily_return_decimal = Decimal(f"{daily_return:.10f}")
        daily_returns.append(daily_return_decimal)
        current_date = observation_date.isoformat()
        source_timestamp = _iso_utc_timestamp(observation_date)
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
        previous_date = observation_date
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


def _build_benchmark_reference_data(
    *,
    dates: list[str],
    start_date: date,
    effective_date: date | None = None,
    economic_anchor: date | None = None,
) -> dict[str, Any]:
    effective_date = effective_date or start_date
    effective_from = effective_date.isoformat()
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
        economic_anchor=economic_anchor,
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
        economic_anchor=economic_anchor,
    )

    benchmark_return_series: list[dict[str, Any]] = []
    for current_date, equity_return, bond_return in zip(
        series_dates, equity_daily_returns, bond_daily_returns, strict=True
    ):
        benchmark_series_specs = (
            (
                DEFAULT_DEMO_BENCHMARK_ID,
                "bmk_global_balanced_60_40_return",
                Decimal("0.6"),
                Decimal("0.4"),
            ),
            (
                SECONDARY_DEMO_BENCHMARK_ID,
                "bmk_global_growth_80_20_return",
                Decimal("0.8"),
                Decimal("0.2"),
            ),
        )
        for benchmark_id, series_id, equity_weight, bond_weight in benchmark_series_specs:
            benchmark_return = (equity_return * equity_weight) + (bond_return * bond_weight)
            benchmark_return_series.append(
                {
                    "series_id": series_id,
                    "benchmark_id": benchmark_id,
                    "series_date": current_date,
                    "benchmark_return": f"{benchmark_return:.10f}",
                    "return_period": "1d",
                    "return_convention": "total_return_index",
                    "series_currency": "USD",
                    "source_timestamp": _iso_utc_timestamp(date.fromisoformat(current_date)),
                    "source_vendor": "LOTUS_DEMO",
                    "source_record_id": f"{series_id}_{current_date}",
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
                "assignment_recorded_at": _iso_utc_timestamp(effective_date, hour=8),
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
                "source_timestamp": _iso_utc_timestamp(effective_date),
                "source_vendor": "LOTUS_DEMO",
                "source_record_id": "bmk_global_balanced_60_40_definition",
            },
            {
                "benchmark_id": SECONDARY_DEMO_BENCHMARK_ID,
                "benchmark_name": "Global Growth 80/20",
                "benchmark_type": "composite",
                "benchmark_currency": "USD",
                "return_convention": "total_return_index",
                "benchmark_status": "active",
                "benchmark_family": "multi_asset_growth",
                "benchmark_provider": "LOTUS_DEMO",
                "rebalance_frequency": "monthly",
                "classification_set_id": "wm_global_taxonomy_v1",
                "classification_labels": {
                    "asset_class": "multi_asset",
                    "strategy": "growth",
                    "region": "global",
                },
                "effective_from": effective_from,
                "source_timestamp": _iso_utc_timestamp(effective_date),
                "source_vendor": "LOTUS_DEMO",
                "source_record_id": "bmk_global_growth_80_20_definition",
            },
        ],
        "benchmark_compositions": [
            {
                "benchmark_id": DEFAULT_DEMO_BENCHMARK_ID,
                "index_id": "IDX_GLOBAL_EQUITY_TR",
                "composition_effective_from": effective_from,
                "composition_weight": "0.6000000000",
                "rebalance_event_id": "bmk_global_balanced_60_40_initial",
                "source_timestamp": _iso_utc_timestamp(effective_date),
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
                "source_timestamp": _iso_utc_timestamp(effective_date),
                "source_vendor": "LOTUS_DEMO",
                "source_record_id": "bmk_global_balanced_60_40_bond",
                "quality_status": "accepted",
            },
            {
                "benchmark_id": SECONDARY_DEMO_BENCHMARK_ID,
                "index_id": "IDX_GLOBAL_EQUITY_TR",
                "composition_effective_from": effective_from,
                "composition_weight": "0.8000000000",
                "rebalance_event_id": "bmk_global_growth_80_20_initial",
                "source_timestamp": _iso_utc_timestamp(effective_date),
                "source_vendor": "LOTUS_DEMO",
                "source_record_id": "bmk_global_growth_80_20_equity",
                "quality_status": "accepted",
            },
            {
                "benchmark_id": SECONDARY_DEMO_BENCHMARK_ID,
                "index_id": "IDX_GLOBAL_BOND_TR",
                "composition_effective_from": effective_from,
                "composition_weight": "0.2000000000",
                "rebalance_event_id": "bmk_global_growth_80_20_initial",
                "source_timestamp": _iso_utc_timestamp(effective_date),
                "source_vendor": "LOTUS_DEMO",
                "source_record_id": "bmk_global_growth_80_20_bond",
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
                    "sector": "broad_market_equity",
                    "region": "global",
                },
                "effective_from": effective_from,
                "source_timestamp": _iso_utc_timestamp(effective_date),
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
                    "sector": "broad_market_fixed_income",
                    "region": "global",
                },
                "effective_from": effective_from,
                "source_timestamp": _iso_utc_timestamp(effective_date),
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
            "catalog_benchmark_ids": [
                DEFAULT_DEMO_BENCHMARK_ID,
                SECONDARY_DEMO_BENCHMARK_ID,
            ],
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


def _normalize_portfolio_ids(portfolio_ids: tuple[str, ...] | None) -> tuple[str, ...] | None:
    if portfolio_ids is None:
        return None
    normalized = tuple(dict.fromkeys(item.strip() for item in portfolio_ids if item.strip()))
    if not normalized:
        return None
    known_ids = {item.portfolio_id for item in DEMO_EXPECTATIONS}
    unknown_ids = sorted(set(normalized) - known_ids)
    if unknown_ids:
        raise ValueError(f"Unknown demo portfolio ids: {', '.join(unknown_ids)}")
    return normalized


def _parse_portfolio_ids(value: str) -> tuple[str, ...] | None:
    return _normalize_portfolio_ids(tuple(value.split(",")))


def _expectations_for_portfolio_ids(
    portfolio_ids: tuple[str, ...] | None,
) -> tuple[PortfolioExpectation, ...]:
    if portfolio_ids is None:
        return DEMO_EXPECTATIONS
    selected_ids = set(portfolio_ids)
    return tuple(item for item in DEMO_EXPECTATIONS if item.portfolio_id in selected_ids)


def build_demo_bundle(
    *,
    history_days: int = DEFAULT_DEMO_HISTORY_DAYS,
    portfolio_ids: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    if history_days < MIN_DEMO_HISTORY_DAYS:
        raise ValueError(f"Demo data history_days must be at least {MIN_DEMO_HISTORY_DAYS}.")
    portfolio_ids = _normalize_portfolio_ids(portfolio_ids)
    start_date, end_date = _demo_pack_date_window(history_days)
    dates = _business_dates(start_date, end_date)
    as_of = end_date.isoformat()
    tx_anchor = DEMO_ECONOMIC_ANCHOR_DATE

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
            "open_date": "2023-01-03",
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
        {
            "security_id": "CASH_USD",
            "name": "US Dollar Cash",
            "isin": "CASH_USD_DEMO",
            "currency": "USD",
            "product_type": "Cash",
            "asset_class": "Cash",
        },
        {
            "security_id": "CASH_EUR",
            "name": "Euro Cash",
            "isin": "CASH_EUR_DEMO",
            "currency": "EUR",
            "product_type": "Cash",
            "asset_class": "Cash",
        },
        {
            "security_id": "CASH_CHF",
            "name": "Swiss Franc Cash",
            "isin": "CASH_CHF_DEMO",
            "currency": "CHF",
            "product_type": "Cash",
            "asset_class": "Cash",
        },
        {
            "security_id": "CASH_SGD",
            "name": "Singapore Dollar Cash",
            "isin": "CASH_SGD_DEMO",
            "currency": "SGD",
            "product_type": "Cash",
            "asset_class": "Cash",
        },
        {
            "security_id": "SEC_AAPL_US",
            "name": "Apple Inc.",
            "isin": "US0378331005",
            "currency": "USD",
            "product_type": "Equity",
            "asset_class": "Equity",
            "sector": "Technology",
            "country_of_risk": "US",
        },
        {
            "security_id": "SEC_SAP_DE",
            "name": "SAP SE",
            "isin": "DE0007164600",
            "currency": "EUR",
            "product_type": "Equity",
            "asset_class": "Equity",
            "sector": "Technology",
            "country_of_risk": "DE",
        },
        {
            "security_id": "SEC_NOVN_CH",
            "name": "Novartis AG",
            "isin": "CH0012005267",
            "currency": "CHF",
            "product_type": "Equity",
            "asset_class": "Equity",
            "sector": "Healthcare",
            "country_of_risk": "CH",
        },
        {
            "security_id": "SEC_SONY_JP",
            "name": "Sony Group Corp.",
            "isin": "JP3435000009",
            "currency": "JPY",
            "product_type": "Equity",
            "asset_class": "Equity",
            "sector": "Consumer Discretionary",
            "country_of_risk": "JP",
        },
        {
            "security_id": "SEC_UST_5Y",
            "name": "US Treasury 5Y",
            "isin": "US91282CGM73",
            "currency": "USD",
            "product_type": "Bond",
            "asset_class": "Fixed Income",
            "rating": "AA+",
            "maturity_date": "2029-08-31",
        },
        {
            "security_id": "SEC_CORP_IG_USD",
            "name": "Global Corp 4.2% 2030",
            "isin": "US0000000001",
            "currency": "USD",
            "product_type": "Bond",
            "asset_class": "Fixed Income",
            "rating": "A-",
            "maturity_date": "2030-06-15",
        },
        {
            "security_id": "SEC_ETF_WORLD_USD",
            "name": "Global Equity ETF",
            "isin": "US0000000002",
            "currency": "USD",
            "product_type": "ETF",
            "asset_class": "Equity",
        },
        {
            "security_id": "SEC_FUND_EM_EQ",
            "name": "Emerging Markets Equity Fund",
            "isin": "LU0000000003",
            "currency": "USD",
            "product_type": "Fund",
            "asset_class": "Equity",
        },
        {
            "security_id": "SEC_GOLD_ETC_USD",
            "name": "Gold ETC",
            "isin": "JE00B1VS3770",
            "currency": "USD",
            "product_type": "ETC",
            "asset_class": "Commodity",
        },
    ]
    txs = [
        _tx(
            "DEMO_ADV_DEP_01",
            "DEMO_ADV_USD_001",
            "CASH",
            "CASH_USD",
            tx_ts(1, 9),
            "DEPOSIT",
            750000,
            1,
            750000,
            "USD",
        ),
        _tx(
            "DEMO_ADV_BUY_AAPL_01",
            "DEMO_ADV_USD_001",
            "AAPL",
            "SEC_AAPL_US",
            tx_ts(2),
            "BUY",
            1200,
            182,
            218400,
            "USD",
        ),
        _tx(
            "DEMO_ADV_CASH_OUT_01",
            "DEMO_ADV_USD_001",
            "CASH",
            "CASH_USD",
            tx_ts(2),
            "SELL",
            218400,
            1,
            218400,
            "USD",
        ),
        _tx(
            "DEMO_ADV_BUY_UST_01",
            "DEMO_ADV_USD_001",
            "UST5Y",
            "SEC_UST_5Y",
            tx_ts(5),
            "BUY",
            180,
            975,
            175500,
            "USD",
        ),
        _tx(
            "DEMO_ADV_CASH_OUT_02",
            "DEMO_ADV_USD_001",
            "CASH",
            "CASH_USD",
            tx_ts(5),
            "SELL",
            175500,
            1,
            175500,
            "USD",
        ),
        _tx(
            "DEMO_ADV_BUY_ETF_01",
            "DEMO_ADV_USD_001",
            "WORLD_ETF",
            "SEC_ETF_WORLD_USD",
            tx_ts(35),
            "BUY",
            650,
            128,
            83200,
            "USD",
        ),
        _tx(
            "DEMO_ADV_CASH_OUT_03",
            "DEMO_ADV_USD_001",
            "CASH",
            "CASH_USD",
            tx_ts(35),
            "SELL",
            83200,
            1,
            83200,
            "USD",
        ),
        _tx(
            "DEMO_ADV_DIV_01",
            "DEMO_ADV_USD_001",
            "AAPL",
            "SEC_AAPL_US",
            tx_ts(160),
            "DIVIDEND",
            0,
            0,
            1800,
            "USD",
        ),
        _tx(
            "DEMO_ADV_CASH_IN_01",
            "DEMO_ADV_USD_001",
            "CASH",
            "CASH_USD",
            tx_ts(160),
            "BUY",
            1800,
            1,
            1800,
            "USD",
        ),
        _tx(
            "DEMO_ADV_COUPON_01",
            "DEMO_ADV_USD_001",
            "UST5Y",
            "SEC_UST_5Y",
            tx_ts(340),
            "DIVIDEND",
            0,
            0,
            950,
            "USD",
        ),
        _tx(
            "DEMO_ADV_CASH_IN_02",
            "DEMO_ADV_USD_001",
            "CASH",
            "CASH_USD",
            tx_ts(340),
            "BUY",
            950,
            1,
            950,
            "USD",
        ),
        _tx(
            "DEMO_ADV_DEP_02",
            "DEMO_ADV_USD_001",
            "CASH",
            "CASH_USD",
            tx_ts(420, 9),
            "DEPOSIT",
            120000,
            1,
            120000,
            "USD",
        ),
        _tx(
            "DEMO_ADV_BUY_AAPL_02",
            "DEMO_ADV_USD_001",
            "AAPL",
            "SEC_AAPL_US",
            tx_ts(510),
            "BUY",
            220,
            196,
            43120,
            "USD",
        ),
        _tx(
            "DEMO_ADV_CASH_OUT_04",
            "DEMO_ADV_USD_001",
            "CASH",
            "CASH_USD",
            tx_ts(510),
            "SELL",
            43120,
            1,
            43120,
            "USD",
        ),
        _tx(
            "DEMO_ADV_SELL_UST_01",
            "DEMO_ADV_USD_001",
            "UST5Y",
            "SEC_UST_5Y",
            tx_ts(675),
            "SELL",
            30,
            992,
            29760,
            "USD",
        ),
        _tx(
            "DEMO_ADV_CASH_IN_03",
            "DEMO_ADV_USD_001",
            "CASH",
            "CASH_USD",
            tx_ts(675),
            "BUY",
            29760,
            1,
            29760,
            "USD",
        ),
        _tx(
            "DEMO_ADV_SELL_ETF_01",
            "DEMO_ADV_USD_001",
            "WORLD_ETF",
            "SEC_ETF_WORLD_USD",
            tx_ts(780),
            "SELL",
            120,
            142,
            17040,
            "USD",
        ),
        _tx(
            "DEMO_ADV_CASH_IN_04",
            "DEMO_ADV_USD_001",
            "CASH",
            "CASH_USD",
            tx_ts(780),
            "BUY",
            17040,
            1,
            17040,
            "USD",
        ),
        _tx(
            "DEMO_ADV_FEE_01",
            "DEMO_ADV_USD_001",
            "CASH",
            "CASH_USD",
            tx_ts(900),
            "FEE",
            1,
            425,
            425,
            "USD",
        ),
        _tx(
            "DEMO_DPM_DEP_01",
            "DEMO_DPM_EUR_001",
            "CASH",
            "CASH_EUR",
            tx_ts(1, 9),
            "DEPOSIT",
            600000,
            1,
            600000,
            "EUR",
        ),
        _tx(
            "DEMO_DPM_BUY_SAP_01",
            "DEMO_DPM_EUR_001",
            "SAP",
            "SEC_SAP_DE",
            tx_ts(3),
            "BUY",
            1500,
            120,
            180000,
            "EUR",
        ),
        _tx(
            "DEMO_DPM_CASH_OUT_01",
            "DEMO_DPM_EUR_001",
            "CASH",
            "CASH_EUR",
            tx_ts(3),
            "SELL",
            180000,
            1,
            180000,
            "EUR",
        ),
        _tx(
            "DEMO_DPM_BUY_ETF_01",
            "DEMO_DPM_EUR_001",
            "WORLD_ETF",
            "SEC_ETF_WORLD_USD",
            tx_ts(12),
            "BUY",
            1000,
            95,
            95000,
            "USD",
        ),
        _tx(
            "DEMO_DPM_CASH_OUT_02",
            "DEMO_DPM_EUR_001",
            "CASH",
            "CASH_EUR",
            tx_ts(12),
            "SELL",
            86000,
            1,
            86000,
            "EUR",
        ),
        _tx(
            "DEMO_DPM_SELL_SAP_01",
            "DEMO_DPM_EUR_001",
            "SAP",
            "SEC_SAP_DE",
            tx_ts(220),
            "SELL",
            300,
            128,
            38400,
            "EUR",
        ),
        _tx(
            "DEMO_DPM_CASH_IN_01",
            "DEMO_DPM_EUR_001",
            "CASH",
            "CASH_EUR",
            tx_ts(220),
            "BUY",
            38400,
            1,
            38400,
            "EUR",
        ),
        _tx(
            "DEMO_INCOME_DEP_01",
            "DEMO_INCOME_CHF_001",
            "CASH",
            "CASH_CHF",
            tx_ts(1, 9),
            "DEPOSIT",
            420000,
            1,
            420000,
            "CHF",
        ),
        _tx(
            "DEMO_INCOME_BUY_NOVN_01",
            "DEMO_INCOME_CHF_001",
            "NOVN",
            "SEC_NOVN_CH",
            tx_ts(4),
            "BUY",
            1000,
            92,
            92000,
            "CHF",
        ),
        _tx(
            "DEMO_INCOME_CASH_OUT_01",
            "DEMO_INCOME_CHF_001",
            "CASH",
            "CASH_CHF",
            tx_ts(4),
            "SELL",
            92000,
            1,
            92000,
            "CHF",
        ),
        _tx(
            "DEMO_INCOME_BUY_BOND_01",
            "DEMO_INCOME_CHF_001",
            "CORP_IG",
            "SEC_CORP_IG_USD",
            tx_ts(8),
            "BUY",
            90,
            1010,
            90900,
            "USD",
        ),
        _tx(
            "DEMO_INCOME_CASH_OUT_02",
            "DEMO_INCOME_CHF_001",
            "CASH",
            "CASH_CHF",
            tx_ts(8),
            "SELL",
            82000,
            1,
            82000,
            "CHF",
        ),
        _tx(
            "DEMO_INCOME_COUPON_01",
            "DEMO_INCOME_CHF_001",
            "CORP_IG",
            "SEC_CORP_IG_USD",
            tx_ts(190),
            "DIVIDEND",
            0,
            0,
            650,
            "USD",
        ),
        _tx(
            "DEMO_INCOME_CASH_IN_01",
            "DEMO_INCOME_CHF_001",
            "CASH",
            "CASH_CHF",
            tx_ts(190),
            "BUY",
            580,
            1,
            580,
            "CHF",
        ),
        _tx(
            "DEMO_BAL_DEP_01",
            "DEMO_BALANCED_SGD_001",
            "CASH",
            "CASH_SGD",
            tx_ts(1, 9),
            "DEPOSIT",
            700000,
            1,
            700000,
            "SGD",
        ),
        _tx(
            "DEMO_BAL_BUY_SONY_01",
            "DEMO_BALANCED_SGD_001",
            "SONY",
            "SEC_SONY_JP",
            tx_ts(3),
            "BUY",
            1200,
            1750,
            2100000,
            "JPY",
        ),
        _tx(
            "DEMO_BAL_CASH_OUT_01",
            "DEMO_BALANCED_SGD_001",
            "CASH",
            "CASH_SGD",
            tx_ts(3),
            "SELL",
            19800,
            1,
            19800,
            "SGD",
        ),
        _tx(
            "DEMO_BAL_BUY_GOLD_01",
            "DEMO_BALANCED_SGD_001",
            "GOLD_ETC",
            "SEC_GOLD_ETC_USD",
            tx_ts(30),
            "BUY",
            500,
            210,
            105000,
            "USD",
        ),
        _tx(
            "DEMO_BAL_CASH_OUT_02",
            "DEMO_BALANCED_SGD_001",
            "CASH",
            "CASH_SGD",
            tx_ts(30),
            "SELL",
            141000,
            1,
            141000,
            "SGD",
        ),
        _tx(
            "DEMO_BAL_SELL_SONY_01",
            "DEMO_BALANCED_SGD_001",
            "SONY",
            "SEC_SONY_JP",
            tx_ts(280),
            "SELL",
            200,
            1820,
            364000,
            "JPY",
        ),
        _tx(
            "DEMO_BAL_CASH_IN_01",
            "DEMO_BALANCED_SGD_001",
            "CASH",
            "CASH_SGD",
            tx_ts(280),
            "BUY",
            3300,
            1,
            3300,
            "SGD",
        ),
        _tx(
            "DEMO_REBAL_DEP_01",
            "DEMO_REBAL_USD_001",
            "CASH",
            "CASH_USD",
            tx_ts(1, 9),
            "DEPOSIT",
            300000,
            1,
            300000,
            "USD",
        ),
        _tx(
            "DEMO_REBAL_BUY_FUND_01",
            "DEMO_REBAL_USD_001",
            "EM_FUND",
            "SEC_FUND_EM_EQ",
            tx_ts(10),
            "BUY",
            2000,
            55,
            110000,
            "USD",
        ),
        _tx(
            "DEMO_REBAL_CASH_OUT_01",
            "DEMO_REBAL_USD_001",
            "CASH",
            "CASH_USD",
            tx_ts(10),
            "SELL",
            110000,
            1,
            110000,
            "USD",
        ),
        _tx(
            "DEMO_REBAL_BUY_BOND_01",
            "DEMO_REBAL_USD_001",
            "CORP_IG",
            "SEC_CORP_IG_USD",
            tx_ts(20),
            "BUY",
            60,
            1012,
            60720,
            "USD",
        ),
        _tx(
            "DEMO_REBAL_CASH_OUT_02",
            "DEMO_REBAL_USD_001",
            "CASH",
            "CASH_USD",
            tx_ts(20),
            "SELL",
            60720,
            1,
            60720,
            "USD",
        ),
        _tx(
            "DEMO_REBAL_TRANSFER_OUT_01",
            "DEMO_REBAL_USD_001",
            "EM_FUND",
            "SEC_FUND_EM_EQ",
            tx_ts(240),
            "TRANSFER_OUT",
            200,
            56,
            11200,
            "USD",
        ),
        _tx(
            "DEMO_REBAL_CASH_IN_01",
            "DEMO_REBAL_USD_001",
            "CASH",
            "CASH_USD",
            tx_ts(240),
            "BUY",
            11200,
            1,
            11200,
            "USD",
        ),
        _tx(
            "DEMO_REBAL_WITHDRAW_01",
            "DEMO_REBAL_USD_001",
            "CASH",
            "CASH_USD",
            tx_ts(340),
            "WITHDRAWAL",
            15000,
            1,
            15000,
            "USD",
        ),
    ]
    if portfolio_ids is not None:
        selected_ids = set(portfolio_ids)
        portfolios = [item for item in portfolios if item["portfolio_id"] in selected_ids]
        txs = [item for item in txs if item["portfolio_id"] in selected_ids]
        needed_security_ids = {item["security_id"] for item in txs}
        instruments = [item for item in instruments if item["security_id"] in needed_security_ids]
    else:
        needed_security_ids = {item["security_id"] for item in instruments}

    transaction_dates = {
        str(item["transaction_date"]).split("T", maxsplit=1)[0]
        for item in txs
        if item.get("transaction_date")
    }
    reference_dates = sorted({*dates, *transaction_dates, as_of})
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
    cash_security_ids = {
        item["security_id"]
        for item in instruments
        if item.get("product_type") == "Cash" and item["security_id"] in needed_security_ids
    }
    for d in reference_dates:
        for security_id, currency in (
            ("CASH_USD", "USD"),
            ("CASH_EUR", "EUR"),
            ("CASH_CHF", "CHF"),
            ("CASH_SGD", "SGD"),
        ):
            if security_id in cash_security_ids:
                market_prices.append(
                    {"security_id": security_id, "price_date": d, "price": 1, "currency": currency}
                )
    for security_id, (start_px, end_px, ccy) in price_paths.items():
        if security_id not in needed_security_ids:
            continue
        for d in reference_dates:
            px = _stable_linear_value(
                observation_date=date.fromisoformat(d),
                anchor_date=DEMO_ECONOMIC_ANCHOR_DATE,
                end_date=DEMO_CANONICAL_AS_OF_DATE,
                start_value=start_px,
                end_value=end_px,
                precision=2,
            )
            market_prices.append(
                {"security_id": security_id, "price_date": d, "price": px, "currency": ccy}
            )
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
    required_currencies = {
        item["base_currency"] for item in portfolios if item.get("base_currency")
    } | {item["trade_currency"] for item in txs if item.get("trade_currency")}
    fx_rates: list[dict[str, Any]] = []
    for (from_ccy, to_ccy), (start_rate, end_rate) in fx_paths.items():
        if required_currencies and (
            from_ccy not in required_currencies or to_ccy not in required_currencies
        ):
            continue
        for d in reference_dates:
            rate = _stable_linear_value(
                observation_date=date.fromisoformat(d),
                anchor_date=DEMO_ECONOMIC_ANCHOR_DATE,
                end_date=DEMO_CANONICAL_AS_OF_DATE,
                start_value=start_rate,
                end_value=end_rate,
                precision=6,
            )
            fx_rates.append(
                {"from_currency": from_ccy, "to_currency": to_ccy, "rate_date": d, "rate": rate}
            )
    benchmark_reference = _build_benchmark_reference_data(
        dates=dates,
        start_date=start_date,
        effective_date=DEMO_BENCHMARK_EFFECTIVE_DATE,
        economic_anchor=DEMO_ECONOMIC_ANCHOR_DATE,
    )
    if portfolio_ids is not None and DEFAULT_DEMO_BENCHMARK_PORTFOLIO_ID not in set(portfolio_ids):
        benchmark_reference = {**benchmark_reference, "benchmark_assignments": []}
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


def _canonical_payload_fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _demo_pack_idempotency_key(*, segment: str, payload: dict[str, Any]) -> str:
    return f"lotus-demo-pack:v2:{segment}:{_canonical_payload_fingerprint(payload)}"


def _canonical_number(value: object) -> str:
    normalized = Decimal(str(value)).normalize()
    return format(normalized, "f")


def _records_cover_expected(
    *,
    expected: list[dict[str, Any]],
    actual: list[dict[str, Any]],
    key_fields: tuple[str, ...],
    compare_fields: tuple[str, ...],
    numeric_fields: frozenset[str] = frozenset(),
    datetime_fields: frozenset[str] = frozenset(),
) -> bool:
    actual_by_key = {
        tuple(str(record.get(field)) for field in key_fields): record for record in actual
    }
    for expected_record in expected:
        key = tuple(str(expected_record.get(field)) for field in key_fields)
        actual_record = actual_by_key.get(key)
        if actual_record is None:
            return False
        for field in compare_fields:
            expected_value = expected_record.get(field)
            actual_value = actual_record.get(field)
            if field in numeric_fields:
                if expected_value is None or actual_value is None:
                    return False
                if _canonical_number(expected_value) != _canonical_number(actual_value):
                    return False
            elif field in datetime_fields:
                if expected_value is None or actual_value is None:
                    return False
                expected_datetime = datetime.fromisoformat(
                    str(expected_value).replace("Z", "+00:00")
                )
                actual_datetime = datetime.fromisoformat(str(actual_value).replace("Z", "+00:00"))
                if expected_datetime != actual_datetime:
                    return False
            elif expected_value != actual_value:
                return False
    return True


def _probe_market_and_fx_segments(
    query_base_url: str,
    segments: tuple[DemoPackSegment, ...],
) -> DemoPackCompleteness:
    evaluated = tuple(
        segment.name
        for segment in segments
        if segment.endpoint in {"/ingest/market-prices", "/ingest/fx-rates"}
    )
    actual_market_prices: dict[str, list[dict[str, Any]]] = {}
    actual_fx_rates: dict[tuple[str, str], list[dict[str, Any]]] = {}

    expected_market_prices = [
        record for segment in segments for record in segment.payload.get("market_prices", [])
    ]
    for security_id in sorted({str(record["security_id"]) for record in expected_market_prices}):
        records = [
            record for record in expected_market_prices if record["security_id"] == security_id
        ]
        params = parse.urlencode(
            {
                "security_id": security_id,
                "start_date": min(str(record["price_date"]) for record in records),
                "end_date": max(str(record["price_date"]) for record in records),
            }
        )
        _, payload = _request_source_json("GET", f"{query_base_url}/prices/?{params}")
        actual_market_prices[security_id] = [
            {"security_id": security_id, **record} for record in payload.get("prices") or []
        ]

    expected_fx_rates = [
        record for segment in segments for record in segment.payload.get("fx_rates", [])
    ]
    pairs = sorted(
        {(str(record["from_currency"]), str(record["to_currency"])) for record in expected_fx_rates}
    )
    for from_currency, to_currency in pairs:
        records = [
            record
            for record in expected_fx_rates
            if record["from_currency"] == from_currency and record["to_currency"] == to_currency
        ]
        params = parse.urlencode(
            {
                "from_currency": from_currency,
                "to_currency": to_currency,
                "start_date": min(str(record["rate_date"]) for record in records),
                "end_date": max(str(record["rate_date"]) for record in records),
            }
        )
        _, payload = _request_source_json("GET", f"{query_base_url}/fx-rates/?{params}")
        actual_fx_rates[(from_currency, to_currency)] = [
            {
                "from_currency": from_currency,
                "to_currency": to_currency,
                **record,
            }
            for record in payload.get("rates") or []
        ]

    missing: list[str] = []
    for segment in segments:
        market_prices = segment.payload.get("market_prices")
        if market_prices is not None:
            actual = [
                record
                for security_id in {str(item["security_id"]) for item in market_prices}
                for record in actual_market_prices.get(security_id, [])
            ]
            if not _records_cover_expected(
                expected=market_prices,
                actual=actual,
                key_fields=("security_id", "price_date"),
                compare_fields=("price", "currency"),
                numeric_fields=frozenset({"price"}),
            ):
                missing.append(segment.name)
        fx_rates = segment.payload.get("fx_rates")
        if fx_rates is not None:
            actual = [
                record
                for pair in {
                    (str(item["from_currency"]), str(item["to_currency"])) for item in fx_rates
                }
                for record in actual_fx_rates.get(pair, [])
            ]
            if not _records_cover_expected(
                expected=fx_rates,
                actual=actual,
                key_fields=("from_currency", "to_currency", "rate_date"),
                compare_fields=("rate",),
                numeric_fields=frozenset({"rate"}),
            ):
                missing.append(segment.name)
    return DemoPackCompleteness(
        evaluated_segments=evaluated,
        missing_segments=tuple(sorted(missing)),
    )


def _probe_index_segments(
    query_control_plane_base_url: str,
    *,
    as_of_date: str,
    segments: tuple[DemoPackSegment, ...],
) -> DemoPackCompleteness:
    by_name = {segment.name: segment for segment in segments}
    evaluated = tuple(
        name for name in ("indices", "index-price-series", "index-return-series") if name in by_name
    )
    missing: list[str] = []

    index_segment = by_name.get("indices")
    if index_segment is not None:
        expected_indices = index_segment.payload["indices"]
        _, response = _request_source_json(
            "POST",
            f"{query_control_plane_base_url}/integration/indices/catalog",
            payload={
                "as_of_date": as_of_date,
                "index_ids": sorted(str(record["index_id"]) for record in expected_indices),
            },
        )
        if not _records_cover_expected(
            expected=expected_indices,
            actual=response.get("records") or [],
            key_fields=("index_id",),
            compare_fields=(
                "index_name",
                "index_currency",
                "index_type",
                "index_status",
                "index_provider",
                "index_market",
                "classification_set_id",
                "classification_labels",
                "effective_from",
                "source_vendor",
                "source_record_id",
            ),
        ):
            missing.append(index_segment.name)

    for segment_name, payload_key, endpoint_suffix, value_field, numeric_field in (
        (
            "index-price-series",
            "index_price_series",
            "price-series",
            "index_price",
            "index_price",
        ),
        (
            "index-return-series",
            "index_return_series",
            "return-series",
            "index_return",
            "index_return",
        ),
    ):
        segment = by_name.get(segment_name)
        if segment is None:
            continue
        expected_records = segment.payload[payload_key]
        actual_records: list[dict[str, Any]] = []
        for index_id in sorted({str(record["index_id"]) for record in expected_records}):
            records = [record for record in expected_records if record["index_id"] == index_id]
            _, response = _request_source_json(
                "POST",
                f"{query_control_plane_base_url}/integration/indices/{index_id}/{endpoint_suffix}",
                payload={
                    "as_of_date": as_of_date,
                    "window": {
                        "start_date": min(str(record["series_date"]) for record in records),
                        "end_date": max(str(record["series_date"]) for record in records),
                    },
                    "frequency": "daily",
                },
            )
            actual_records.extend(
                {"index_id": index_id, **record} for record in response.get("points") or []
            )
        common_fields = (
            value_field,
            "series_currency",
            "quality_status",
        )
        series_fields = (
            (*common_fields, "value_convention")
            if segment_name == "index-price-series"
            else (*common_fields, "return_period", "return_convention")
        )
        if not _records_cover_expected(
            expected=expected_records,
            actual=actual_records,
            key_fields=("index_id", "series_date"),
            compare_fields=series_fields,
            numeric_fields=frozenset({numeric_field}),
        ):
            missing.append(segment.name)

    return DemoPackCompleteness(
        evaluated_segments=evaluated,
        missing_segments=tuple(sorted(missing)),
    )


def _probe_benchmark_and_risk_free_segments(
    query_control_plane_base_url: str,
    *,
    as_of_date: str,
    segments: tuple[DemoPackSegment, ...],
) -> DemoPackCompleteness:
    by_name = {segment.name: segment for segment in segments}
    supported_names = (
        "benchmark-definitions",
        "benchmark-compositions",
        "benchmark-return-series",
        "benchmark-assignments",
        "risk-free-series",
    )
    evaluated = tuple(name for name in supported_names if name in by_name)
    missing: list[str] = []

    definitions = by_name.get("benchmark-definitions")
    if definitions is not None:
        expected = definitions.payload["benchmark_definitions"]
        _, response = _request_source_json(
            "POST",
            f"{query_control_plane_base_url}/integration/benchmarks/catalog",
            payload={"as_of_date": as_of_date},
        )
        if not _records_cover_expected(
            expected=expected,
            actual=response.get("records") or [],
            key_fields=("benchmark_id",),
            compare_fields=(
                "benchmark_name",
                "benchmark_type",
                "benchmark_currency",
                "return_convention",
                "benchmark_status",
                "benchmark_family",
                "benchmark_provider",
                "rebalance_frequency",
                "classification_set_id",
                "classification_labels",
                "effective_from",
                "source_vendor",
                "source_record_id",
            ),
        ):
            missing.append(definitions.name)

    compositions = by_name.get("benchmark-compositions")
    if compositions is not None:
        expected = compositions.payload["benchmark_compositions"]
        actual_compositions: list[dict[str, Any]] = []
        for benchmark_id in sorted({str(record["benchmark_id"]) for record in expected}):
            records = [record for record in expected if record["benchmark_id"] == benchmark_id]
            _, response = _request_source_json(
                "POST",
                (
                    f"{query_control_plane_base_url}/integration/benchmarks/"
                    f"{benchmark_id}/composition-window"
                ),
                payload={
                    "window": {
                        "start_date": min(
                            str(record["composition_effective_from"]) for record in records
                        ),
                        "end_date": as_of_date,
                    }
                },
            )
            actual_compositions.extend(
                {"benchmark_id": benchmark_id, **record}
                for record in response.get("segments") or []
            )
        if not _records_cover_expected(
            expected=expected,
            actual=actual_compositions,
            key_fields=("benchmark_id", "index_id", "composition_effective_from"),
            compare_fields=("composition_weight", "rebalance_event_id"),
            numeric_fields=frozenset({"composition_weight"}),
        ):
            missing.append(compositions.name)

    returns = by_name.get("benchmark-return-series")
    if returns is not None:
        expected = returns.payload["benchmark_return_series"]
        actual_returns: list[dict[str, Any]] = []
        for benchmark_id in sorted({str(record["benchmark_id"]) for record in expected}):
            records = [record for record in expected if record["benchmark_id"] == benchmark_id]
            _, response = _request_source_json(
                "POST",
                (
                    f"{query_control_plane_base_url}/integration/benchmarks/"
                    f"{benchmark_id}/return-series"
                ),
                payload={
                    "as_of_date": as_of_date,
                    "window": {
                        "start_date": min(str(record["series_date"]) for record in records),
                        "end_date": max(str(record["series_date"]) for record in records),
                    },
                    "frequency": "daily",
                },
            )
            actual_returns.extend(
                {"benchmark_id": benchmark_id, **record} for record in response.get("points") or []
            )
        if not _records_cover_expected(
            expected=expected,
            actual=actual_returns,
            key_fields=("benchmark_id", "series_date"),
            compare_fields=(
                "benchmark_return",
                "return_period",
                "return_convention",
                "series_currency",
                "quality_status",
            ),
            numeric_fields=frozenset({"benchmark_return"}),
        ):
            missing.append(returns.name)

    assignments = by_name.get("benchmark-assignments")
    if assignments is not None:
        expected = assignments.payload["benchmark_assignments"]
        actual_assignments: list[dict[str, Any]] = []
        for record in expected:
            portfolio_id = str(record["portfolio_id"])
            _, response = _request_source_json(
                "POST",
                (
                    f"{query_control_plane_base_url}/integration/portfolios/"
                    f"{portfolio_id}/benchmark-assignment"
                ),
                payload={"as_of_date": as_of_date},
            )
            actual_assignments.append(response)
        if not _records_cover_expected(
            expected=expected,
            actual=actual_assignments,
            key_fields=("portfolio_id",),
            compare_fields=(
                "benchmark_id",
                "effective_from",
                "assignment_source",
                "assignment_status",
                "policy_pack_id",
                "source_system",
                "assignment_version",
            ),
            numeric_fields=frozenset({"assignment_version"}),
        ):
            missing.append(assignments.name)

    risk_free = by_name.get("risk-free-series")
    if risk_free is not None:
        expected = risk_free.payload["risk_free_series"]
        actual_risk_free_points: list[dict[str, Any]] = []
        for currency in sorted({str(record["series_currency"]) for record in expected}):
            records = [record for record in expected if record["series_currency"] == currency]
            series_modes = {
                (
                    "annualized_rate_series"
                    if record["value_convention"] == "annualized_rate"
                    else "return_series"
                )
                for record in records
            }
            for series_mode in sorted(series_modes):
                mode_records = [
                    record
                    for record in records
                    if (
                        "annualized_rate_series"
                        if record["value_convention"] == "annualized_rate"
                        else "return_series"
                    )
                    == series_mode
                ]
                _, response = _request_source_json(
                    "POST",
                    f"{query_control_plane_base_url}/integration/reference/risk-free-series",
                    payload={
                        "as_of_date": as_of_date,
                        "window": {
                            "start_date": min(
                                str(record["series_date"]) for record in mode_records
                            ),
                            "end_date": max(str(record["series_date"]) for record in mode_records),
                        },
                        "frequency": "daily",
                        "currency": currency,
                        "series_mode": series_mode,
                    },
                )
                actual_risk_free_points.extend(response.get("points") or [])
        if not _records_cover_expected(
            expected=expected,
            actual=actual_risk_free_points,
            key_fields=("series_currency", "series_date", "value_convention"),
            compare_fields=(
                "value",
                "day_count_convention",
                "compounding_convention",
                "quality_status",
            ),
            numeric_fields=frozenset({"value"}),
        ):
            missing.append(risk_free.name)

    return DemoPackCompleteness(
        evaluated_segments=evaluated,
        missing_segments=tuple(sorted(missing)),
    )


def _probe_portfolio_bundle_segment(
    query_base_url: str,
    query_control_plane_base_url: str,
    *,
    as_of_date: str,
    segment: DemoPackSegment,
    expectations: tuple[PortfolioExpectation, ...],
) -> DemoPackCompleteness:
    if segment.name != "portfolio-bundle":
        raise ValueError("Portfolio completeness requires the portfolio-bundle segment")
    payload = segment.payload
    expected_portfolios = payload["portfolios"]
    actual_portfolios: list[dict[str, Any]] = []
    for portfolio in expected_portfolios:
        portfolio_id = str(portfolio["portfolio_id"])
        _, response = _request_source_json("GET", f"{query_base_url}/portfolios/{portfolio_id}")
        actual_portfolios.append(response)
    complete = _records_cover_expected(
        expected=expected_portfolios,
        actual=actual_portfolios,
        key_fields=("portfolio_id",),
        compare_fields=(
            "base_currency",
            "open_date",
            "risk_exposure",
            "investment_time_horizon",
            "portfolio_type",
            "booking_center_code",
            "client_id",
            "status",
            "cost_basis_method",
        ),
    )

    expected_instruments = payload["instruments"]
    actual_instruments: list[dict[str, Any]] = []
    for instrument in expected_instruments:
        params = parse.urlencode({"security_id": instrument["security_id"], "limit": 2})
        _, response = _request_source_json("GET", f"{query_base_url}/instruments/?{params}")
        actual_instruments.extend(response.get("instruments") or [])
    instrument_fields = (
        "name",
        "isin",
        "currency",
        "product_type",
        "asset_class",
        "sector",
        "country_of_risk",
        "rating",
        "liquidity_tier",
    )
    complete = complete and _records_cover_expected(
        expected=expected_instruments,
        actual=actual_instruments,
        key_fields=("security_id",),
        compare_fields=tuple(
            field
            for field in instrument_fields
            if any(field in row for row in expected_instruments)
        ),
    )

    expected_business_dates = [str(record["business_date"]) for record in payload["business_dates"]]
    calendar_portfolio_id = str(expected_portfolios[0]["portfolio_id"])
    calendar_window = {
        "start_date": min(expected_business_dates),
        "end_date": max(expected_business_dates),
    }
    _, calendar_response = _request_source_json(
        "POST",
        (
            f"{query_control_plane_base_url}/integration/portfolios/"
            f"{calendar_portfolio_id}/analytics/portfolio-timeseries"
        ),
        payload={
            "as_of_date": as_of_date,
            "window": calendar_window,
            "frequency": "daily",
            "consumer_system": "lotus-core-demo-data-loader",
            "page": {"page_size": 1},
        },
    )
    calendar_diagnostics = calendar_response.get("diagnostics") or {}
    complete = complete and (
        calendar_response.get("resolved_window") == calendar_window
        and calendar_diagnostics.get("expected_business_dates_count")
        == len(expected_business_dates)
        and calendar_diagnostics.get("missing_dates_count") == 0
    )

    transaction_fields = (
        "transaction_date",
        "settlement_date",
        "transaction_type",
        "instrument_id",
        "security_id",
        "quantity",
        "price",
        "gross_transaction_amount",
        "trade_currency",
        "currency",
        "cash_entry_mode",
        "settlement_cash_account_id",
        "settlement_cash_instrument_id",
        "movement_direction",
        "originating_transaction_id",
        "originating_transaction_type",
        "adjustment_reason",
        "link_type",
        "reconciliation_key",
    )
    for portfolio in expected_portfolios:
        portfolio_id = str(portfolio["portfolio_id"])
        expected_transactions = [
            record for record in payload["transactions"] if record["portfolio_id"] == portfolio_id
        ]
        params = parse.urlencode({"limit": 200, "as_of_date": as_of_date})
        _, response = _request_source_json(
            "GET",
            f"{query_base_url}/portfolios/{portfolio_id}/transactions?{params}",
        )
        actual_transactions = response.get("transactions") or []
        compared_fields = tuple(
            field
            for field in transaction_fields
            if any(field in record for record in expected_transactions)
        )
        complete = complete and _records_cover_expected(
            expected=expected_transactions,
            actual=actual_transactions,
            key_fields=("transaction_id",),
            compare_fields=compared_fields,
            numeric_fields=frozenset(
                {"quantity", "price", "gross_transaction_amount"}.intersection(compared_fields)
            ),
            datetime_fields=frozenset(
                {"transaction_date", "settlement_date"}.intersection(compared_fields)
            ),
        )

    expectations_by_id = {expectation.portfolio_id: expectation for expectation in expectations}
    for portfolio in expected_portfolios:
        portfolio_id = str(portfolio["portfolio_id"])
        expectation = expectations_by_id.get(portfolio_id)
        if expectation is None:
            complete = False
            continue
        params = parse.urlencode({"as_of_date": as_of_date, "include_projected": "false"})
        _, response = _request_source_json(
            "GET",
            f"{query_base_url}/portfolios/{portfolio_id}/positions?{params}",
        )
        actual_positions = response.get("positions") or []
        expected_positions = [
            {"security_id": security_id, "quantity": quantity}
            for security_id, quantity in expectation.expected_terminal_quantities
        ]
        complete = complete and _records_cover_expected(
            expected=expected_positions,
            actual=actual_positions,
            key_fields=("security_id",),
            compare_fields=("quantity",),
            numeric_fields=frozenset({"quantity"}),
        )

    return DemoPackCompleteness(
        evaluated_segments=(segment.name,),
        missing_segments=() if complete else (segment.name,),
    )


def _build_logical_series_segments(
    *,
    records: list[dict[str, Any]],
    payload_key: str,
    endpoint: str,
    segment_prefix: str,
    identity_fields: tuple[str, ...],
    date_field: str,
) -> list[DemoPackSegment]:
    records_by_identity: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for record in records:
        identity = tuple(str(record[field]) for field in identity_fields)
        records_by_identity.setdefault(identity, []).append(record)

    segments: list[DemoPackSegment] = []
    for identity in sorted(records_by_identity):
        identity_token = ":".join(identity)
        ordered_records = sorted(
            records_by_identity[identity],
            key=lambda record: str(record[date_field]),
        )
        segments.append(
            DemoPackSegment(
                name=f"{segment_prefix}:{identity_token}",
                endpoint=endpoint,
                payload={payload_key: ordered_records},
                category="portfolio",
            )
        )
    return segments


def _build_demo_pack_segments(bundle: dict[str, Any]) -> tuple[DemoPackSegment, ...]:
    portfolio_payload = _build_portfolio_bundle_payload(bundle)
    market_prices = portfolio_payload.pop("market_prices")
    fx_rates = portfolio_payload.pop("fx_rates")
    segments = [
        DemoPackSegment(
            name="portfolio-bundle",
            endpoint="/ingest/portfolio-bundle",
            payload=portfolio_payload,
            category="portfolio",
        )
    ]
    segments.extend(
        _build_logical_series_segments(
            records=market_prices,
            payload_key="market_prices",
            endpoint="/ingest/market-prices",
            segment_prefix="market-prices",
            identity_fields=("security_id",),
            date_field="price_date",
        )
    )
    segments.extend(
        _build_logical_series_segments(
            records=fx_rates,
            payload_key="fx_rates",
            endpoint="/ingest/fx-rates",
            segment_prefix="fx-rates",
            identity_fields=("from_currency", "to_currency"),
            date_field="rate_date",
        )
    )

    reference_payloads = (
        ("indices", "/ingest/indices", {"indices": bundle["indices"]}),
        (
            "index-price-series",
            "/ingest/index-price-series",
            {"index_price_series": bundle["index_price_series"]},
        ),
        (
            "index-return-series",
            "/ingest/index-return-series",
            {"index_return_series": bundle["index_return_series"]},
        ),
        (
            "benchmark-definitions",
            "/ingest/benchmark-definitions",
            {"benchmark_definitions": bundle["benchmark_definitions"]},
        ),
        (
            "benchmark-compositions",
            "/ingest/benchmark-compositions",
            {"benchmark_compositions": bundle["benchmark_compositions"]},
        ),
        (
            "benchmark-return-series",
            "/ingest/benchmark-return-series",
            {"benchmark_return_series": bundle["benchmark_return_series"]},
        ),
        (
            "benchmark-assignments",
            "/ingest/benchmark-assignments",
            {"benchmark_assignments": bundle["benchmark_assignments"]},
        ),
        (
            "risk-free-series",
            "/ingest/risk-free-series",
            {"risk_free_series": bundle["risk_free_series"]},
        ),
    )
    segments.extend(
        DemoPackSegment(
            name=name,
            endpoint=endpoint,
            payload=payload,
            category="reference",
        )
        for name, endpoint, payload in reference_payloads
        if any(not isinstance(value, list) or value for value in payload.values())
    )
    names = [segment.name for segment in segments]
    if len(names) != len(set(names)):
        raise ValueError("Demo pack segment names must be unique")
    return tuple(segments)


def _post_demo_pack_payload(
    ingestion_base_url: str,
    *,
    endpoint: str,
    segment: str,
    payload: dict[str, Any],
    force_ingest: bool,
) -> DemoPackIngestionOutcome:
    idempotency_key = None
    headers = None
    if not force_ingest:
        idempotency_key = _demo_pack_idempotency_key(segment=segment, payload=payload)
        headers = {"X-Idempotency-Key": idempotency_key}

    _, response = _request_json(
        "POST",
        f"{ingestion_base_url}{endpoint}",
        payload=payload,
        headers=headers,
    )
    if not isinstance(response, dict):
        raise RuntimeError(f"Demo pack ingestion returned a non-object acknowledgement: {endpoint}")
    if idempotency_key is not None and response.get("idempotency_key") != idempotency_key:
        raise RuntimeError(
            f"Demo pack ingestion acknowledgement did not preserve its idempotency key: {endpoint}"
        )
    return DemoPackIngestionOutcome(
        segment=segment,
        replayed=response.get("message") == IDEMPOTENCY_REPLAY_MESSAGE,
        idempotency_key=idempotency_key,
    )


def _ingest_demo_segments(
    ingestion_base_url: str,
    segments: tuple[DemoPackSegment, ...],
    *,
    force_ingest: bool,
) -> list[DemoPackIngestionOutcome]:
    outcomes: list[DemoPackIngestionOutcome] = []
    for segment in segments:
        LOGGER.info(
            "Ingesting demo segment name=%s records=%d.",
            segment.name,
            segment.record_count,
        )
        outcomes.append(
            _post_demo_pack_payload(
                ingestion_base_url,
                endpoint=segment.endpoint,
                segment=segment.name,
                payload=segment.payload,
                force_ingest=force_ingest,
            )
        )
    return outcomes


def _request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    req = request.Request(
        url=url,
        method=method.upper(),
        data=(None if payload is None else json.dumps(payload).encode("utf-8")),
        headers=request_headers,
    )
    try:
        with request.urlopen(req, timeout=15) as response:
            body = response.read().decode("utf-8")
            return response.status, (json.loads(body) if body else {})
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise DemoPackHttpError(
            method=method,
            url=url,
            status_code=exc.code,
            detail=detail,
        ) from exc
    except (error.URLError, http.client.RemoteDisconnected, TimeoutError, ConnectionError) as exc:
        raise RuntimeError(f"{method} {url} connection error: {exc}") from exc


def _request_source_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    try:
        return _request_json(method, url, payload=payload)
    except DemoPackHttpError as exc:
        if exc.status_code == 404:
            return exc.status_code, {}
        raise


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


def _probe_demo_pack_completeness(
    *,
    query_base_url: str,
    query_control_plane_base_url: str,
    bundle: dict[str, Any],
    expectations: tuple[PortfolioExpectation, ...],
) -> DemoPackCompleteness:
    segments = _build_demo_pack_segments(bundle)
    portfolio_segment = next(segment for segment in segments if segment.name == "portfolio-bundle")
    results = (
        _probe_portfolio_bundle_segment(
            query_base_url,
            query_control_plane_base_url,
            as_of_date=bundle["as_of_date"],
            segment=portfolio_segment,
            expectations=expectations,
        ),
        _probe_market_and_fx_segments(query_base_url, segments),
        _probe_index_segments(
            query_control_plane_base_url,
            as_of_date=bundle["as_of_date"],
            segments=segments,
        ),
        _probe_benchmark_and_risk_free_segments(
            query_control_plane_base_url,
            as_of_date=bundle["as_of_date"],
            segments=segments,
        ),
    )
    evaluated = tuple(
        dict.fromkeys(name for result in results for name in result.evaluated_segments)
    )
    expected_names = tuple(segment.name for segment in segments)
    if set(evaluated) != set(expected_names):
        unevaluated = sorted(set(expected_names).difference(evaluated))
        raise RuntimeError(
            "Demo pack completeness probe did not evaluate every segment: " + ", ".join(unevaluated)
        )
    return DemoPackCompleteness(
        evaluated_segments=evaluated,
        missing_segments=tuple(
            sorted({name for result in results for name in result.missing_segments})
        ),
    )


def _ingest_demo_pack_if_needed(
    *,
    ingestion_base_url: str,
    query_base_url: str,
    query_control_plane_base_url: str,
    bundle: dict[str, Any],
    expectations: tuple[PortfolioExpectation, ...],
    force_ingest: bool,
) -> bool:
    segments = _build_demo_pack_segments(bundle)
    pack_fingerprint = _canonical_payload_fingerprint(bundle)
    if force_ingest:
        selected_segments = segments
        decision_reason = "explicit_force_refresh"
    else:
        completeness = _probe_demo_pack_completeness(
            query_base_url=query_base_url,
            query_control_plane_base_url=query_control_plane_base_url,
            bundle=bundle,
            expectations=expectations,
        )
        if completeness.is_complete:
            LOGGER.info(
                (
                    "Demo pack is complete; startup is a source-verified no-op "
                    "reason=unchanged_pack_present pack_fingerprint=sha256:%s segments=%d"
                ),
                pack_fingerprint,
                len(completeness.evaluated_segments),
            )
            return False
        missing = set(completeness.missing_segments)
        selected_segments = tuple(segment for segment in segments if segment.name in missing)
        decision_reason = "missing_or_evolved_segments_selected"

    if not selected_segments:
        raise RuntimeError("Demo pack ingestion decision selected no segments")
    LOGGER.info(
        "Demo pack ingestion selection reason=%s segments=%s.",
        decision_reason,
        ",".join(segment.name for segment in selected_segments),
    )
    outcomes = _ingest_demo_segments(
        ingestion_base_url,
        selected_segments,
        force_ingest=force_ingest,
    )
    replayed_segments = sorted(item.segment for item in outcomes if item.replayed)
    published_segments = sorted(item.segment for item in outcomes if not item.replayed)

    if outcomes and not published_segments:
        LOGGER.info(
            (
                "Selected demo pack segments were durable idempotency replays; "
                "reason=selected_segments_already_published pack_fingerprint=sha256:%s "
                "segments=%s"
            ),
            pack_fingerprint,
            ",".join(replayed_segments),
        )
        return False

    LOGGER.info(
        (
            "Demo pack ingestion decision reason=%s pack_fingerprint=sha256:%s "
            "published_segments=%s replayed_segment_count=%d benchmark=%s "
            "assigned_portfolio=%s"
        ),
        decision_reason,
        pack_fingerprint,
        ",".join(published_segments),
        len(replayed_segments),
        bundle["benchmark_verification"]["benchmark_id"],
        bundle["benchmark_verification"]["portfolio_id"],
    )
    return True


def _format_verification_state(state: dict[str, Any]) -> str:
    return ", ".join(f"{key}={value}" for key, value in state.items())


def _verify_portfolio(
    query_base_url: str,
    expected: PortfolioExpectation,
    as_of_date: str,
    wait_seconds: int,
    poll_interval_seconds: int,
) -> dict[str, Any]:
    deadline = time.time() + wait_seconds
    last_observed: dict[str, Any] = {
        "portfolio_id": expected.portfolio_id,
        "status": "not_observed",
    }
    while time.time() < deadline:
        try:
            position_params = parse.urlencode({"as_of_date": as_of_date})
            _, pos_payload = _request_json(
                "GET",
                (
                    f"{query_base_url}/portfolios/{expected.portfolio_id}/positions"
                    f"?{position_params}"
                ),
            )
            _, tx_payload = _request_json(
                "GET", f"{query_base_url}/portfolios/{expected.portfolio_id}/transactions?limit=200"
            )
        except RuntimeError as exc:
            last_observed = {
                "portfolio_id": expected.portfolio_id,
                "status": "connection_error",
                "error": str(exc),
            }
            time.sleep(poll_interval_seconds)
            continue
        positions = pos_payload.get("positions") or []
        valued = [
            p
            for p in positions
            if isinstance(p.get("valuation"), dict)
            and p["valuation"].get("market_value") is not None
        ]
        total_transactions = int(tx_payload.get("total", 0))
        all_quantities_match = True
        quantity_checks: list[str] = []
        positions_by_security = {
            str(position.get("security_id")): position for position in positions
        }
        for security_id, expected_quantity in expected.expected_terminal_quantities:
            position = positions_by_security.get(security_id)
            if position is None:
                quantity_checks.append(f"{security_id}:missing_position")
                all_quantities_match = False
                break
            actual_quantity = float(position.get("quantity", 0.0))
            if abs(actual_quantity - expected_quantity) > 1e-6:
                quantity_checks.append(
                    f"{security_id}:actual={actual_quantity:g}:expected={expected_quantity:g}"
                )
                all_quantities_match = False
                break
            quantity_checks.append(f"{security_id}:matched")
        last_observed = {
            "portfolio_id": expected.portfolio_id,
            "positions": len(positions),
            "min_positions": expected.min_positions,
            "valued_positions": len(valued),
            "min_valued_positions": expected.min_valued_positions,
            "transactions": total_transactions,
            "min_transactions": expected.min_transactions,
            "quantity_checks": ";".join(quantity_checks),
        }
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
    raise TimeoutError(
        "Timed out verifying portfolio outputs for "
        f"{expected.portfolio_id}; last_observed=({_format_verification_state(last_observed)})."
    )


def _verify_benchmark_reference(
    query_control_plane_base_url: str,
    *,
    portfolio_id: str,
    benchmark_id: str,
    catalog_benchmark_ids: list[str],
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
            composition_payload.get("segments") if isinstance(composition_payload, dict) else None
        )
        if (
            isinstance(records, list)
            and all(
                any(record.get("benchmark_id") == expected_id for record in records)
                for expected_id in catalog_benchmark_ids
            )
            and isinstance(assignment_payload, dict)
            and assignment_payload.get("benchmark_id") == benchmark_id
            and isinstance(segments, list)
            and segments
        ):
            return {
                "portfolio_id": portfolio_id,
                "benchmark_id": benchmark_id,
                "catalog_benchmark_ids": catalog_benchmark_ids,
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
    parser.add_argument(
        "--history-days",
        type=int,
        default=365 * 3,
        help=(
            "Calendar-day lookback window used to generate demo market, FX, benchmark, "
            "and risk-free history. The default preserves the rich app-local demo pack; "
            "CI latency gates may use a smaller bounded window to reduce unrelated backfill."
        ),
    )
    parser.add_argument(
        "--portfolio-ids",
        default="",
        help=(
            "Optional comma-separated demo portfolio ids to seed and verify. Empty value preserves "
            "the full demo pack. CI latency gates use this to load only the measured portfolio."
        ),
    )
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
    portfolio_ids = _parse_portfolio_ids(args.portfolio_ids)
    expectations = _expectations_for_portfolio_ids(portfolio_ids)
    _wait_ready(f"{ingestion_base_url}/health/ready", args.wait_seconds, args.poll_interval_seconds)
    _wait_ready(f"{query_base_url}/health/ready", args.wait_seconds, args.poll_interval_seconds)
    _wait_ready(
        f"{query_control_plane_base_url}/health/ready",
        args.wait_seconds,
        args.poll_interval_seconds,
    )
    demo_bundle = build_demo_bundle(history_days=args.history_days, portfolio_ids=portfolio_ids)
    if not args.verify_only:
        _ingest_demo_pack_if_needed(
            ingestion_base_url=ingestion_base_url,
            query_base_url=query_base_url,
            query_control_plane_base_url=query_control_plane_base_url,
            bundle=demo_bundle,
            expectations=expectations,
            force_ingest=args.force_ingest,
        )
    if not args.ingest_only:
        verification_results: list[dict[str, Any]] = []
        for expected in expectations:
            result = _verify_portfolio(
                query_base_url,
                expected,
                demo_bundle["as_of_date"],
                args.wait_seconds,
                args.poll_interval_seconds,
            )
            verification_results.append(result)
            LOGGER.info(
                (
                    "Verified portfolio %s (positions=%d valued_positions=%d "
                    "transactions=%d holdings_validated=%d)"
                ),
                result["portfolio_id"],
                result["positions"],
                result["valued_positions"],
                result["transactions"],
                result["validated_holdings"],
            )
        benchmark_portfolio_id = demo_bundle["benchmark_verification"]["portfolio_id"]
        if portfolio_ids is None or benchmark_portfolio_id in set(portfolio_ids):
            benchmark_result = _verify_benchmark_reference(
                query_control_plane_base_url,
                portfolio_id=benchmark_portfolio_id,
                benchmark_id=demo_bundle["benchmark_verification"]["benchmark_id"],
                catalog_benchmark_ids=demo_bundle["benchmark_verification"][
                    "catalog_benchmark_ids"
                ],
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
        else:
            LOGGER.info(
                "Skipped benchmark verification for %s because selected demo portfolios are %s.",
                benchmark_portfolio_id,
                ",".join(portfolio_ids),
            )
        if len(verification_results) != len(expectations):
            raise RuntimeError("Demo verification failed: not all demo portfolios were verified.")
    LOGGER.info("Demo data pack workflow completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
