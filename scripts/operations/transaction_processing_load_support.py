"""Shared domain fixtures and completion probes for transaction runtime gates."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import requests  # type: ignore[import-untyped]
from prometheus_client.parser import text_string_to_metric_families
from sqlalchemy import Engine, text

_TRANSACTION_PROCESSING_OPERATION_METRIC = "lotus_core_transaction_processing_operations_total"


@dataclass(frozen=True, slots=True)
class TransactionProcessingCounts:
    transaction_count: int
    cost_count: int
    cashflow_count: int
    position_count: int
    processing_claim_count: int


def build_transaction_batch(
    *,
    portfolio_id: str,
    batch_size: int,
    seed: str,
    transaction_date: str,
    security_prefix: str = "SEC",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(batch_size):
        transaction_suffix = f"{seed}-{index:04d}"
        rows.append(
            {
                "transaction_id": f"TX_{transaction_suffix}",
                "portfolio_id": portfolio_id,
                "instrument_id": f"{security_prefix}_{index % 20:03d}",
                "security_id": f"{security_prefix}_{index % 20:03d}",
                "transaction_date": transaction_date,
                "transaction_type": "BUY",
                "quantity": "10",
                "price": "100.00",
                "gross_transaction_amount": "1000.00",
                "trade_currency": "USD",
                "currency": "USD",
            }
        )
    return rows


def ingest_transactions(
    *,
    ingestion_base_url: str,
    portfolio_id: str,
    batches: int,
    batch_size: int,
    sleep_seconds_between_batches: float,
    seed_prefix: str,
    security_prefix: str,
    transaction_date: str,
) -> tuple[list[str], int]:
    transaction_ids: list[str] = []
    total_batches = 0
    for batch_number in range(batches):
        seed = f"{seed_prefix}-{uuid4().hex[:8]}-{batch_number:03d}"
        transactions = build_transaction_batch(
            portfolio_id=portfolio_id,
            batch_size=batch_size,
            seed=seed,
            transaction_date=transaction_date,
            security_prefix=security_prefix,
        )
        response = requests.post(
            f"{ingestion_base_url}/ingest/transactions",
            json={"transactions": transactions},
            timeout=30,
        )
        if response.status_code != 202:
            raise RuntimeError(
                "Transaction ingestion failed with "
                f"status={response.status_code}: {response.text[:300]}"
            )
        transaction_ids.extend(str(item["transaction_id"]) for item in transactions)
        total_batches += 1
        if sleep_seconds_between_batches > 0:
            time.sleep(sleep_seconds_between_batches)
    return transaction_ids, total_batches


def seed_load_context(
    *,
    engine: Engine,
    ingestion_base_url: str,
    run_id: str,
    portfolio_id: str,
    security_prefix: str,
    business_date: str,
    timeout_seconds: int,
) -> None:
    _post_ingestion_records(
        ingestion_base_url=ingestion_base_url,
        endpoint="/ingest/business-dates",
        root_key="business_dates",
        rows=[{"business_date": business_date}],
    )
    wait_for_database_count(
        engine=engine,
        sql="SELECT count(*) FROM business_dates WHERE date = :value",
        params={"value": business_date},
        expected=1,
        label="transaction load business-date seed",
        timeout_seconds=timeout_seconds,
    )
    _post_ingestion_records(
        ingestion_base_url=ingestion_base_url,
        endpoint="/ingest/portfolios",
        root_key="portfolios",
        rows=[
            {
                "portfolio_id": portfolio_id,
                "portfolio_name": f"Performance Load {run_id}",
                "base_currency": "USD",
                "open_date": business_date,
                "risk_exposure": "BALANCED",
                "investment_time_horizon": "MEDIUM_TERM",
                "portfolio_type": "DISCRETIONARY",
                "booking_center_code": "PB_SG",
                "client_id": f"PERF_CLIENT_{run_id}",
                "status": "ACTIVE",
            }
        ],
    )
    wait_for_database_count(
        engine=engine,
        sql="SELECT count(*) FROM portfolios WHERE portfolio_id = :value",
        params={"value": portfolio_id},
        expected=1,
        label="transaction load portfolio seed",
        timeout_seconds=timeout_seconds,
    )

    instruments = [
        {
            "security_id": f"{security_prefix}_{index:03d}",
            "name": f"Performance Load Security {index:03d}",
            "isin": f"USPF{run_id[-4:]}{index:04d}"[:12],
            "currency": "USD",
            "product_type": "STOCK",
            "asset_class": "EQUITY",
            "sector": "DIVERSIFIED",
            "country_of_risk": "US",
        }
        for index in range(20)
    ]
    _post_ingestion_records(
        ingestion_base_url=ingestion_base_url,
        endpoint="/ingest/instruments",
        root_key="instruments",
        rows=instruments,
    )
    wait_for_database_count(
        engine=engine,
        sql="SELECT count(*) FROM instruments WHERE security_id LIKE :value",
        params={"value": f"{security_prefix}_%"},
        expected=20,
        label="transaction load instrument seed",
        timeout_seconds=timeout_seconds,
    )


def wait_for_database_count(
    *,
    engine: Engine,
    sql: str,
    params: dict[str, object],
    expected: int,
    label: str,
    timeout_seconds: int,
) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        with engine.connect() as connection:
            actual = int(connection.execute(text(sql), params).scalar_one())
        if actual == expected:
            return
        time.sleep(1)
    raise TimeoutError(f"{label} did not reach expected count {expected}")


def wait_for_transaction_processing(
    *,
    engine: Engine,
    portfolio_id: str,
    transaction_id_prefix: str,
    expected: int,
    expected_processing_claim_minimum: int,
    timeout_seconds: int,
) -> float | None:
    started = time.time()
    deadline = started + timeout_seconds
    while time.time() < deadline:
        counts = transaction_processing_counts(
            engine=engine,
            portfolio_id=portfolio_id,
            transaction_id_prefix=transaction_id_prefix,
        )
        domain_counts_match = all(
            count == expected
            for count in (
                counts.transaction_count,
                counts.cost_count,
                counts.cashflow_count,
                counts.position_count,
            )
        )
        if (
            domain_counts_match
            and counts.processing_claim_count >= expected_processing_claim_minimum
        ):
            return round(time.time() - started, 3)
        time.sleep(1)
    return None


def transaction_processing_counts(
    *,
    engine: Engine,
    portfolio_id: str,
    transaction_id_prefix: str,
) -> TransactionProcessingCounts:
    query = text(
        """
        SELECT
          count(*) AS transaction_count,
          count(*) FILTER (
            WHERE gross_cost IS NOT NULL
              AND net_cost IS NOT NULL
              AND transaction_fx_rate IS NOT NULL
          ) AS cost_count,
          (SELECT count(*) FROM cashflows WHERE transaction_id LIKE :pattern) AS cashflow_count,
          (SELECT count(*) FROM position_history WHERE transaction_id LIKE :pattern)
            AS position_count,
          (SELECT count(*) FROM processed_events
             WHERE portfolio_id = :portfolio_id
               AND service_name = 'portfolio-transaction-processing') AS processing_claim_count
        FROM transactions
        WHERE transaction_id LIKE :pattern
        """
    )
    with engine.connect() as connection:
        row = (
            connection.execute(
                query,
                {
                    "pattern": f"{transaction_id_prefix}%",
                    "portfolio_id": portfolio_id,
                },
            )
            .mappings()
            .one()
        )
    return TransactionProcessingCounts(
        transaction_count=int(row["transaction_count"]),
        cost_count=int(row["cost_count"]),
        cashflow_count=int(row["cashflow_count"]),
        position_count=int(row["position_count"]),
        processing_claim_count=int(row["processing_claim_count"]),
    )


def processed_event_count(*, engine: Engine, portfolio_id: str) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                text(
                    """
                    SELECT count(*)
                    FROM processed_events
                    WHERE portfolio_id = :portfolio_id
                      AND service_name = 'portfolio-transaction-processing'
                    """
                ),
                {"portfolio_id": portfolio_id},
            ).scalar_one()
        )


def transaction_processing_operation_count(
    *,
    transaction_processing_base_url: str,
    stage: str,
    outcome: str,
) -> int:
    response = requests.get(
        f"{transaction_processing_base_url}/metrics",
        timeout=10,
    )
    response.raise_for_status()
    for family in text_string_to_metric_families(response.text):
        for sample in family.samples:
            if (
                sample.name == _TRANSACTION_PROCESSING_OPERATION_METRIC
                and sample.labels.get("stage") == stage
                and sample.labels.get("outcome") == outcome
            ):
                return int(sample.value)
    return 0


def wait_for_transaction_processing_operation_count(
    *,
    transaction_processing_base_url: str,
    stage: str,
    outcome: str,
    expected_minimum: int,
    timeout_seconds: int,
) -> float | None:
    started = time.time()
    deadline = started + timeout_seconds
    while time.time() < deadline:
        if (
            transaction_processing_operation_count(
                transaction_processing_base_url=transaction_processing_base_url,
                stage=stage,
                outcome=outcome,
            )
            >= expected_minimum
        ):
            return round(time.time() - started, 3)
        time.sleep(1)
    return None


def _post_ingestion_records(
    *,
    ingestion_base_url: str,
    endpoint: str,
    root_key: str,
    rows: list[dict[str, Any]],
) -> None:
    response = requests.post(
        f"{ingestion_base_url}{endpoint}",
        json={root_key: rows},
        timeout=30,
    )
    if response.status_code != 202:
        raise RuntimeError(
            f"Reference seed failed endpoint={endpoint} status={response.status_code}: "
            f"{response.text[:300]}"
        )
