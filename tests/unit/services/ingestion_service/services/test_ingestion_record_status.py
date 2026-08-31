from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from src.services.ingestion_service.app.services.ingestion_record_status import (
    build_record_status_response,
    failed_record_keys_from_failures,
    load_record_status_response,
    replayable_record_keys_from_payload,
)


@dataclass(slots=True)
class _Failure:
    failed_record_keys: list[Any] | None


class _SingleSessionAsyncIterable:
    def __init__(self, session):
        self._session = session
        self._yielded = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._yielded:
            raise StopAsyncIteration
        self._yielded = True
        return self._session


class _FakeScalarRows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


def _replayable_job(**overrides: object) -> SimpleNamespace:
    values = {
        "job_id": "job_123",
        "endpoint": "/ingest/transactions",
        "entity_type": "transaction",
        "accepted_count": 3,
        "request_payload": {
            "transactions": [
                {"transaction_id": "txn_1"},
                {"transaction_id": "txn_2"},
            ]
        },
        "request_payload_policy_version": "ingestion-evidence-policy.v1",
        "request_payload_representation": "source_safe_replay",
        "request_payload_replay_eligible": True,
        "request_payload_replay_expires_at": datetime(2099, 1, 1, tzinfo=UTC),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


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


def test_build_record_status_response_maps_job_and_failures():
    job = _replayable_job()
    failures = [_Failure(["txn_2", "txn_3"])]

    response = build_record_status_response(job=job, failures=failures)

    assert response.job_id == "job_123"
    assert response.entity_type == "transaction"
    assert response.accepted_count == 3
    assert response.failed_record_keys == ["txn_2", "txn_3"]
    assert response.replayable_record_keys == ["txn_1", "txn_2"]


def test_build_record_status_response_ignores_malformed_request_payload():
    job = _replayable_job(
        job_id="job_456",
        accepted_count=1,
        request_payload=["not", "a", "dict"],
    )

    response = build_record_status_response(job=job, failures=[])

    assert response.job_id == "job_456"
    assert response.failed_record_keys == []
    assert response.replayable_record_keys == []


@pytest.mark.parametrize(
    "authority_override",
    [
        {"request_payload_policy_version": "legacy.v0"},
        {"request_payload_replay_eligible": False},
        {"request_payload_representation": "fingerprint_only"},
        {"request_payload_replay_expires_at": None},
    ],
)
def test_build_record_status_response_does_not_publish_unauthorized_replay_keys(
    authority_override: dict[str, object],
) -> None:
    response = build_record_status_response(
        job=_replayable_job(**authority_override),
        failures=[],
        observed_at=datetime(2026, 8, 14, tzinfo=UTC),
    )

    assert response.replayable_record_keys == []


def test_build_record_status_response_stops_reporting_keys_at_exact_expiry() -> None:
    expiry = datetime(2026, 8, 14, tzinfo=UTC)
    job = _replayable_job(request_payload_replay_expires_at=expiry)

    before_expiry = build_record_status_response(
        job=job,
        failures=[],
        observed_at=expiry - timedelta(microseconds=1),
    )
    at_expiry = build_record_status_response(
        job=job,
        failures=[],
        observed_at=expiry,
    )

    assert before_expiry.replayable_record_keys == ["txn_1", "txn_2"]
    assert at_expiry.replayable_record_keys == []


@pytest.mark.asyncio
async def test_load_record_status_response_returns_none_for_missing_job():
    class _FakeSession:
        async def scalar(self, _stmt):
            return None

    response = await load_record_status_response(
        job_id="missing",
        tenant_id="tenant-test",
        session_factory=lambda: _SingleSessionAsyncIterable(_FakeSession()),
    )

    assert response is None


@pytest.mark.asyncio
async def test_load_record_status_response_loads_job_and_ordered_failures():
    now = datetime.now(UTC)
    job = _replayable_job(
        job_id="job_789",
        endpoint="/ingest/portfolios",
        entity_type="portfolio",
        accepted_count=2,
        request_payload={"portfolios": [{"portfolio_id": "portfolio_1"}]},
    )
    failures = [
        SimpleNamespace(
            failed_record_keys=["portfolio_2"],
            failed_at=now,
        )
    ]

    class _FakeSession:
        async def scalar(self, _stmt):
            return job

        async def scalars(self, _stmt):
            return _FakeScalarRows(failures)

    response = await load_record_status_response(
        job_id="job_789",
        tenant_id="tenant-test",
        session_factory=lambda: _SingleSessionAsyncIterable(_FakeSession()),
    )

    assert response is not None
    assert response.job_id == "job_789"
    assert response.failed_record_keys == ["portfolio_2"]
    assert response.replayable_record_keys == ["portfolio_1"]
