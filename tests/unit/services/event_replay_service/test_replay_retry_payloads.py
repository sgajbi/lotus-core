from datetime import date

import pytest

from src.services.event_replay_service.app.application.replay_retry_payloads import (
    MissingReplayRecordKeysError,
    deterministic_replay_fingerprint,
    filter_payload_by_record_keys,
    payload_record_count,
)


def test_filter_payload_by_record_keys_returns_original_payload_without_record_keys() -> None:
    payload = {"transactions": [{"transaction_id": "T1"}]}

    filtered = filter_payload_by_record_keys(
        endpoint="/ingest/transactions",
        payload=payload,
        record_keys=[],
    )

    assert filtered is payload


@pytest.mark.parametrize(
    ("endpoint", "payload", "record_keys", "expected"),
    [
        (
            "/ingest/transactions",
            {"transactions": [{"transaction_id": "T1"}, {"transaction_id": "T2"}]},
            ["T2"],
            {"transactions": [{"transaction_id": "T2"}]},
        ),
        (
            "/ingest/portfolios",
            {"portfolios": [{"portfolio_id": "P1"}, {"portfolio_id": "P2"}]},
            ["P1"],
            {"portfolios": [{"portfolio_id": "P1"}]},
        ),
        (
            "/ingest/instruments",
            {"instruments": [{"security_id": "S1"}, {"security_id": "S2"}]},
            ["S2"],
            {"instruments": [{"security_id": "S2"}]},
        ),
        (
            "/ingest/business-dates",
            {"business_dates": [{"business_date": date(2026, 6, 22)}]},
            ["2026-06-22"],
            {"business_dates": [{"business_date": date(2026, 6, 22)}]},
        ),
        (
            "/reprocess/transactions",
            {"transaction_ids": ["T1", "T2", "T3"]},
            ["T1", "T3"],
            {"transaction_ids": ["T1", "T3"]},
        ),
    ],
)
def test_filter_payload_by_record_keys_filters_supported_partial_retry_payloads(
    endpoint: str,
    payload: dict,
    record_keys: list[str],
    expected: dict,
) -> None:
    assert (
        filter_payload_by_record_keys(
            endpoint=endpoint,
            payload=payload,
            record_keys=record_keys,
        )
        == expected
    )


def test_filter_payload_by_record_keys_rejects_unsupported_partial_retry_endpoint() -> None:
    with pytest.raises(ValueError, match="Partial retry is not supported"):
        filter_payload_by_record_keys(
            endpoint="/ingest/market-prices",
            payload={"market_prices": [{"security_id": "S1"}]},
            record_keys=["S1"],
        )


@pytest.mark.parametrize(
    ("endpoint", "payload", "record_keys", "missing_record_keys"),
    [
        (
            "/ingest/transactions",
            {"transactions": [{"transaction_id": "T1"}]},
            ["T1", "T2"],
            ["T2"],
        ),
        (
            "/reprocess/transactions",
            {"transaction_ids": ["T1"]},
            ["T2", "T3"],
            ["T2", "T3"],
        ),
    ],
)
def test_filter_payload_by_record_keys_rejects_missing_requested_keys(
    endpoint: str,
    payload: dict,
    record_keys: list[str],
    missing_record_keys: list[str],
) -> None:
    with pytest.raises(MissingReplayRecordKeysError) as exc_info:
        filter_payload_by_record_keys(
            endpoint=endpoint,
            payload=payload,
            record_keys=record_keys,
        )

    assert exc_info.value.missing_record_keys == missing_record_keys


def test_payload_record_count_uses_largest_list_payload() -> None:
    assert (
        payload_record_count(
            {
                "transactions": [{"transaction_id": "T1"}, {"transaction_id": "T2"}],
                "metadata": {"source": "fixture"},
            }
        )
        == 2
    )


def test_payload_record_count_handles_scalar_payload_and_missing_payload() -> None:
    assert payload_record_count({"status": "ready"}) == 1
    assert payload_record_count(None) == 0


def test_deterministic_replay_fingerprint_is_stable_across_payload_key_order() -> None:
    left = deterministic_replay_fingerprint(
        event_id="event-001",
        correlation_id="corr-001",
        job_id="job-001",
        endpoint="/ingest/transactions",
        payload={"b": 2, "a": 1},
        idempotency_key="idem-001",
    )
    right = deterministic_replay_fingerprint(
        event_id="event-001",
        correlation_id="corr-001",
        job_id="job-001",
        endpoint="/ingest/transactions",
        payload={"a": 1, "b": 2},
        idempotency_key="idem-001",
    )

    assert left == right
    assert len(left) == 64
