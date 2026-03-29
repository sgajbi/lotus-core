from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib import request

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.demo_data_pack import (  # noqa: E402
    DEFAULT_DEMO_BENCHMARK_ID,
    _build_benchmark_reference_data,
)

LOGGER = logging.getLogger("manual_performance_seed")

DEFAULT_PORTFOLIO_ID = "MANUAL_PB_USD_001"
DEFAULT_INGESTION_BASE_URL = "http://127.0.0.1:8200"
DEFAULT_QUERY_CONTROL_BASE_URL = "http://127.0.0.1:8202"
DEFAULT_GATEWAY_BASE_URL = "http://127.0.0.1:8100"
DEFAULT_POSTGRES_CONTAINER = "lotus-core-app-local-postgres-1"


@dataclass(frozen=True)
class ManualSecuritySeed:
    security_id: str
    end_price: Decimal
    currency: str
    start_multiplier: Decimal


MANUAL_SECURITY_SEEDS: tuple[ManualSecuritySeed, ...] = (
    ManualSecuritySeed("CASH_EUR_MANUAL_PB_001", Decimal("1.0"), "EUR", Decimal("1.0")),
    ManualSecuritySeed("CASH_USD_MANUAL_PB_001", Decimal("1.0"), "USD", Decimal("1.0")),
    ManualSecuritySeed("EQ_DE_SAP_MANUAL_001", Decimal("165.0"), "EUR", Decimal("0.955")),
    ManualSecuritySeed("EQ_US_AAPL_MANUAL_001", Decimal("210.0"), "USD", Decimal("0.945")),
    ManualSecuritySeed("EQ_US_MSFT_MANUAL_001", Decimal("425.0"), "USD", Decimal("0.952")),
    ManualSecuritySeed(
        "FD_EU_BLACKROCK_ALLOC_MANUAL_001", Decimal("108.4"), "EUR", Decimal("0.982")
    ),
    ManualSecuritySeed(
        "FD_US_PIMCO_INC_MANUAL_001", Decimal("102.4"), "USD", Decimal("0.988")
    ),
    ManualSecuritySeed(
        "FI_EU_SIEMENS_2031_MANUAL_001", Decimal("99.25"), "EUR", Decimal("0.992")
    ),
    ManualSecuritySeed(
        "FI_US_TSY_2030_MANUAL_001", Decimal("101.35"), "USD", Decimal("0.994")
    ),
)

BENCHMARK_INDEX_IDS: tuple[str, str] = ("IDX_GLOBAL_EQUITY_TR", "IDX_GLOBAL_BOND_TR")


def _business_dates(start: date, end: date) -> list[date]:
    dates: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)
    return dates


def _calendar_dates(start: date, end: date) -> list[date]:
    dates: list[date] = []
    current = start
    while current <= end:
        dates.append(current)
        current += timedelta(days=1)
    return dates


def _iso_utc_timestamp(day: date, hour: int = 21) -> str:
    return (
        datetime(day.year, day.month, day.day, hour=hour, tzinfo=UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


def build_manual_seed_cleanup_sql(*, portfolio_id: str, benchmark_id: str) -> str:
    quoted_index_ids = ", ".join(f"'{index_id}'" for index_id in BENCHMARK_INDEX_IDS)
    return "\n".join(
        [
            (
                "delete from portfolio_benchmark_assignments "
                f"where portfolio_id = '{portfolio_id}' and benchmark_id = '{benchmark_id}';"
            ),
            f"delete from benchmark_composition_series where benchmark_id = '{benchmark_id}';",
            f"delete from benchmark_return_series where benchmark_id = '{benchmark_id}';",
            f"delete from benchmark_definitions where benchmark_id = '{benchmark_id}';",
            f"delete from index_price_series where index_id in ({quoted_index_ids});",
            f"delete from index_return_series where index_id in ({quoted_index_ids});",
            f"delete from index_definitions where index_id in ({quoted_index_ids});",
        ]
    )


def _interpolate_series(
    *,
    dates: list[date],
    end_value: Decimal,
    start_multiplier: Decimal,
    precision: str,
) -> list[str]:
    if not dates:
        return []
    if len(dates) == 1:
        return [format(end_value.quantize(Decimal(precision)), "f")]
    start_value = end_value * start_multiplier
    denominator = Decimal(len(dates) - 1)
    values: list[str] = []
    for index, _current in enumerate(dates):
        ratio = Decimal(index) / denominator
        value = start_value + ((end_value - start_value) * ratio)
        values.append(format(value.quantize(Decimal(precision)), "f"))
    return values


def build_manual_performance_seed_bundle(
    *,
    portfolio_id: str,
    start_date: date,
    end_date: date,
    benchmark_start_date: date | None = None,
    benchmark_id: str = DEFAULT_DEMO_BENCHMARK_ID,
) -> dict[str, Any]:
    effective_benchmark_start_date = benchmark_start_date or start_date
    business_dates = _business_dates(start_date, end_date)
    iso_dates = [current.isoformat() for current in business_dates]
    calendar_dates = _calendar_dates(start_date, end_date)
    calendar_iso_dates = [current.isoformat() for current in calendar_dates]

    market_prices: list[dict[str, Any]] = []
    for security in MANUAL_SECURITY_SEEDS:
        series_values = _interpolate_series(
            dates=business_dates,
            end_value=security.end_price,
            start_multiplier=security.start_multiplier,
            precision="0.0000000001",
        )
        for current_date, price in zip(iso_dates, series_values, strict=True):
            market_prices.append(
                {
                    "security_id": security.security_id,
                    "price_date": current_date,
                    "price": price,
                    "currency": security.currency,
                }
            )

    eur_usd_values = _interpolate_series(
        dates=calendar_dates,
        end_value=Decimal("1.1100000000"),
        start_multiplier=Decimal("0.98198198198"),
        precision="0.0000010000",
    )
    usd_eur_values = [
        format((Decimal("1") / Decimal(rate)).quantize(Decimal("0.0000010000")), "f")
        for rate in eur_usd_values
    ]
    fx_rates: list[dict[str, Any]] = []
    for current_date, eur_usd, usd_eur in zip(
        calendar_iso_dates,
        eur_usd_values,
        usd_eur_values,
        strict=True,
    ):
        fx_rates.extend(
            [
                {
                    "from_currency": "EUR",
                    "to_currency": "USD",
                    "rate_date": current_date,
                    "rate": eur_usd,
                },
                {
                    "from_currency": "USD",
                    "to_currency": "EUR",
                    "rate_date": current_date,
                    "rate": usd_eur,
                },
            ]
        )

    benchmark_reference = _build_benchmark_reference_data(
        dates=calendar_iso_dates,
        start_date=effective_benchmark_start_date,
    )
    benchmark_reference["benchmark_assignments"] = [
        {
            **assignment,
            "portfolio_id": portfolio_id,
            "benchmark_id": benchmark_id,
            "effective_from": effective_benchmark_start_date.isoformat(),
            "assignment_source": "manual_performance_seed",
            "source_system": "LOTUS_CORE_MANUAL_PORTFOLIO_SEED",
        }
        for assignment in benchmark_reference["benchmark_assignments"]
    ]
    benchmark_reference["benchmark_definitions"] = [
        {
            **definition,
            "benchmark_id": benchmark_id,
            "source_record_id": f"{benchmark_id.lower()}_definition",
        }
        for definition in benchmark_reference["benchmark_definitions"]
    ]
    benchmark_reference["benchmark_compositions"] = [
        {
            **composition,
            "benchmark_id": benchmark_id,
            "source_record_id": f"{benchmark_id.lower()}_{composition['index_id'].lower()}",
        }
        for composition in benchmark_reference["benchmark_compositions"]
    ]
    benchmark_reference["benchmark_return_series"] = [
        {
            **series_row,
            "series_id": f"{benchmark_id.lower()}_return",
            "benchmark_id": benchmark_id,
            "source_record_id": f"{benchmark_id.lower()}_return_{series_row['series_date']}",
        }
        for series_row in benchmark_reference["benchmark_return_series"]
    ]
    benchmark_reference["benchmark_verification"] = {
        **benchmark_reference["benchmark_verification"],
        "portfolio_id": portfolio_id,
        "benchmark_id": benchmark_id,
    }

    return {
        "portfolio_id": portfolio_id,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "benchmark_start_date": effective_benchmark_start_date.isoformat(),
        "business_dates": [{"business_date": current_date} for current_date in iso_dates],
        "market_prices": market_prices,
        "fx_rates": fx_rates,
        **benchmark_reference,
    }


def _post_json(url: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=60) as response:
        raw = response.read().decode("utf-8")
        return response.status, json.loads(raw) if raw else {}


def cleanup_existing_manual_seed(
    *,
    postgres_container: str,
    portfolio_id: str,
    benchmark_id: str,
) -> None:
    sql = build_manual_seed_cleanup_sql(portfolio_id=portfolio_id, benchmark_id=benchmark_id)
    subprocess.run(
        [
            "docker",
            "exec",
            postgres_container,
            "psql",
            "-U",
            "user",
            "-d",
            "portfolio_db",
            "-c",
            sql,
        ],
        check=True,
    )


def ingest_manual_performance_seed(
    *,
    ingestion_base_url: str,
    bundle: dict[str, Any],
) -> None:
    payloads = (
        ("/ingest/business-dates", {"business_dates": bundle["business_dates"]}),
        ("/ingest/market-prices", {"market_prices": bundle["market_prices"]}),
        ("/ingest/fx-rates", {"fx_rates": bundle["fx_rates"]}),
        ("/ingest/indices", {"indices": bundle["indices"]}),
        ("/ingest/index-price-series", {"index_price_series": bundle["index_price_series"]}),
        ("/ingest/index-return-series", {"index_return_series": bundle["index_return_series"]}),
        (
            "/ingest/benchmark-definitions",
            {"benchmark_definitions": bundle["benchmark_definitions"]},
        ),
        (
            "/ingest/benchmark-compositions",
            {"benchmark_compositions": bundle["benchmark_compositions"]},
        ),
        (
            "/ingest/benchmark-return-series",
            {"benchmark_return_series": bundle["benchmark_return_series"]},
        ),
        (
            "/ingest/benchmark-assignments",
            {"benchmark_assignments": bundle["benchmark_assignments"]},
        ),
    )
    for path, payload in payloads:
        status_code, response_payload = _post_json(f"{ingestion_base_url}{path}", payload)
        LOGGER.info("Ingested %s status=%s response=%s", path, status_code, response_payload)


def verify_manual_performance_seed(
    *,
    query_control_base_url: str,
    gateway_base_url: str,
    portfolio_id: str,
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    assignment_payload = {
        "as_of_date": end_date.isoformat(),
        "consumer_system": "lotus-performance",
    }
    timeseries_payload = {
        "as_of_date": end_date.isoformat(),
        "window": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "reporting_currency": "USD",
        "frequency": "daily",
        "include_cash_flows": True,
        "consumer_system": "lotus-performance",
    }
    assignment_status, assignment_response = _post_json(
        f"{query_control_base_url}/integration/portfolios/{portfolio_id}/benchmark-assignment",
        assignment_payload,
    )
    timeseries_status, timeseries_response = _post_json(
        f"{query_control_base_url}/integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries",
        timeseries_payload,
    )
    with request.urlopen(
        f"{gateway_base_url}/api/v1/workbench/{portfolio_id}/performance/summary"
        f"?period=YTD&chart_frequency=monthly&contribution_dimension=asset_class"
        f"&attribution_dimension=asset_class&detail_basis=NET",
        timeout=60,
    ) as response:
        performance_summary = json.loads(response.read().decode("utf-8"))
    return {
        "assignment_status": assignment_status,
        "assignment_response": assignment_response,
        "timeseries_status": timeseries_status,
        "timeseries_response": timeseries_response,
        "performance_summary": performance_summary,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed manual portfolio benchmark and performance inputs for lotus-performance."
    )
    parser.add_argument("--portfolio-id", default=DEFAULT_PORTFOLIO_ID)
    parser.add_argument("--start-date", default="2026-03-03")
    parser.add_argument("--end-date", default="2026-03-28")
    parser.add_argument("--benchmark-start-date", default="2026-01-05")
    parser.add_argument("--benchmark-id", default=DEFAULT_DEMO_BENCHMARK_ID)
    parser.add_argument("--ingestion-base-url", default=DEFAULT_INGESTION_BASE_URL)
    parser.add_argument("--query-control-base-url", default=DEFAULT_QUERY_CONTROL_BASE_URL)
    parser.add_argument("--gateway-base-url", default=DEFAULT_GATEWAY_BASE_URL)
    parser.add_argument("--postgres-container", default=DEFAULT_POSTGRES_CONTAINER)
    parser.add_argument("--skip-cleanup", action="store_true")
    parser.add_argument("--sleep-seconds", type=int, default=20)
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = parse_args()
    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)
    benchmark_start_date = date.fromisoformat(args.benchmark_start_date)

    bundle = build_manual_performance_seed_bundle(
        portfolio_id=args.portfolio_id,
        start_date=start_date,
        end_date=end_date,
        benchmark_start_date=benchmark_start_date,
        benchmark_id=args.benchmark_id,
    )
    LOGGER.info(
        (
            "Prepared manual performance seed bundle: business_dates=%s "
            "market_prices=%s fx_rates=%s benchmark_returns=%s"
        ),
        len(bundle["business_dates"]),
        len(bundle["market_prices"]),
        len(bundle["fx_rates"]),
        len(bundle["benchmark_return_series"]),
    )
    if not args.skip_cleanup:
        cleanup_existing_manual_seed(
            postgres_container=args.postgres_container,
            portfolio_id=args.portfolio_id,
            benchmark_id=args.benchmark_id,
        )
    ingest_manual_performance_seed(ingestion_base_url=args.ingestion_base_url, bundle=bundle)
    LOGGER.info("Waiting %s seconds for downstream valuation and aggregation.", args.sleep_seconds)
    time.sleep(args.sleep_seconds)
    verification = verify_manual_performance_seed(
        query_control_base_url=args.query_control_base_url,
        gateway_base_url=args.gateway_base_url,
        portfolio_id=args.portfolio_id,
        start_date=start_date,
        end_date=end_date,
    )
    print(json.dumps(verification, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
