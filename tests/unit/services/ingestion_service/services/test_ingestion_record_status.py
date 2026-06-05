from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.services.ingestion_service.app.services.ingestion_record_status import (
    failed_record_keys_from_failures,
    replayable_record_keys_from_payload,
)


@dataclass(slots=True)
class _Failure:
    failed_record_keys: list[Any] | None


def test_failed_record_keys_from_failures_filters_and_sorts_strings():
    failures = [
        _Failure(["txn_2", "txn_1", 123, None]),
        _Failure(["txn_2", "txn_3"]),
        _Failure(None),
    ]

    assert failed_record_keys_from_failures(failures) == ["txn_1", "txn_2", "txn_3"]


def test_replayable_record_keys_from_payload_maps_supported_ingestion_endpoints():
    assert replayable_record_keys_from_payload(
        endpoint="/ingest/transactions",
        payload={
            "transactions": [
                {"transaction_id": "txn_1"},
                {"transaction_id": ""},
                {"transaction_id": "txn_2"},
            ]
        },
    ) == ["txn_1", "txn_2"]
    assert replayable_record_keys_from_payload(
        endpoint="/ingest/portfolios",
        payload={"portfolios": [{"portfolio_id": "portfolio_1"}]},
    ) == ["portfolio_1"]
    assert replayable_record_keys_from_payload(
        endpoint="/ingest/instruments",
        payload={"instruments": [{"security_id": "sec_1"}]},
    ) == ["sec_1"]
    assert replayable_record_keys_from_payload(
        endpoint="/ingest/business-dates",
        payload={"business_dates": [{"business_date": "2026-06-05"}]},
    ) == ["2026-06-05"]


def test_replayable_record_keys_from_payload_ignores_unknown_or_malformed_payload():
    assert replayable_record_keys_from_payload(endpoint="/ingest/unknown", payload={}) == []
    assert (
        replayable_record_keys_from_payload(
            endpoint="/ingest/transactions",
            payload=None,
        )
        == []
    )
    assert replayable_record_keys_from_payload(
        endpoint="/ingest/transactions",
        payload={"transactions": [{"transaction_id": "txn_1"}, "bad-row", {}]},
    ) == ["txn_1"]
