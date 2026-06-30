from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.event_replay_service.app.application.replay_payload_dispatcher import (
    IngestionServiceReplayPayloadDispatcher,
)
from src.services.event_replay_service.app.routers.ingestion_operations import (
    _consumer_dlq_replay_candidate_or_response,
    _filter_payload_by_record_keys,
)


def test_filter_payload_by_record_keys_returns_original_payload_without_record_keys() -> None:
    payload = {"transactions": [{"transaction_id": "T1"}]}

    filtered = _filter_payload_by_record_keys(
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
        _filter_payload_by_record_keys(
            endpoint=endpoint,
            payload=payload,
            record_keys=record_keys,
        )
        == expected
    )


def test_filter_payload_by_record_keys_rejects_unsupported_partial_retry_endpoint() -> None:
    with pytest.raises(ValueError, match="Partial retry is not supported"):
        _filter_payload_by_record_keys(
            endpoint="/ingest/market-prices",
            payload={"market_prices": [{"security_id": "S1"}]},
            record_keys=["S1"],
        )


@pytest.mark.asyncio
async def test_replay_payload_dispatcher_dispatches_list_field_payload_with_idempotency_key() -> (
    None
):
    ingestion_service = MagicMock()
    ingestion_service.publish_business_dates = AsyncMock()

    dispatcher = IngestionServiceReplayPayloadDispatcher(ingestion_service)

    await dispatcher.replay_payload(
        endpoint="/ingest/business-dates",
        payload={"business_dates": [{"business_date": "2026-06-22"}]},
        idempotency_key="idem-001",
    )

    ingestion_service.publish_business_dates.assert_awaited_once()
    args, kwargs = ingestion_service.publish_business_dates.await_args
    assert [business_date.business_date for business_date in args[0]] == [date(2026, 6, 22)]
    assert kwargs == {"idempotency_key": "idem-001"}


@pytest.mark.asyncio
async def test_replay_payload_dispatcher_dispatches_whole_portfolio_bundle_request() -> None:
    ingestion_service = MagicMock()
    ingestion_service.publish_portfolio_bundle = AsyncMock()

    dispatcher = IngestionServiceReplayPayloadDispatcher(ingestion_service)

    await dispatcher.replay_payload(
        endpoint="/ingest/portfolio-bundle",
        payload={"business_dates": [{"business_date": "2026-06-22"}]},
        idempotency_key="idem-002",
    )

    ingestion_service.publish_portfolio_bundle.assert_awaited_once()
    args, kwargs = ingestion_service.publish_portfolio_bundle.await_args
    assert args[0].business_dates[0].business_date == date(2026, 6, 22)
    assert kwargs == {"idempotency_key": "idem-002"}


@pytest.mark.asyncio
async def test_replay_payload_dispatcher_rejects_unsupported_endpoint() -> None:
    dispatcher = IngestionServiceReplayPayloadDispatcher(MagicMock())

    with pytest.raises(ValueError, match="Retry not supported"):
        await dispatcher.replay_payload(
            endpoint="/ingest/not-supported",
            payload={},
            idempotency_key=None,
        )


@pytest.mark.asyncio
async def test_consumer_dlq_replay_candidate_records_no_correlated_job_response() -> None:
    ingestion_job_service = MagicMock()
    ingestion_job_service.list_jobs = AsyncMock(return_value=([], 0))
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(return_value="audit-001")

    response = await _consumer_dlq_replay_candidate_or_response(
        event_id="dlq-001",
        correlation_id="corr-001",
        dry_run=True,
        ingestion_job_service=ingestion_job_service,
        requested_by="ops",
    )

    assert response.replay_status == "not_replayable"
    assert response.job_id is None
    assert response.message == "No correlated ingestion job found for consumer DLQ event."
    ingestion_job_service.record_consumer_dlq_replay_audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_consumer_dlq_replay_candidate_records_missing_payload_response() -> None:
    ingestion_job_service = MagicMock()
    ingestion_job_service.list_jobs = AsyncMock(
        return_value=([{"job_id": "job-001", "correlation_id": "corr-001", "status": "failed"}], 1)
    )
    ingestion_job_service.get_job_replay_context = AsyncMock(
        return_value=SimpleNamespace(
            endpoint="/ingest/transactions",
            request_payload=None,
            idempotency_key="idem-001",
        )
    )
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock(return_value="audit-002")

    response = await _consumer_dlq_replay_candidate_or_response(
        event_id="dlq-001",
        correlation_id="corr-001",
        dry_run=False,
        ingestion_job_service=ingestion_job_service,
        requested_by="ops",
    )

    assert response.replay_status == "not_replayable"
    assert response.job_id == "job-001"
    assert response.message == "Correlated ingestion job does not have durable replay payload."
    ingestion_job_service.record_consumer_dlq_replay_audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_consumer_dlq_replay_candidate_returns_replayable_context() -> None:
    context = SimpleNamespace(
        endpoint="/ingest/transactions",
        request_payload={"transactions": [{"transaction_id": "T1"}]},
        idempotency_key="idem-001",
    )
    ingestion_job_service = MagicMock()
    ingestion_job_service.list_jobs = AsyncMock(
        return_value=(
            [SimpleNamespace(job_id="job-001", correlation_id="corr-001", status="queued")],
            1,
        )
    )
    ingestion_job_service.get_job_replay_context = AsyncMock(return_value=context)
    ingestion_job_service.record_consumer_dlq_replay_audit = AsyncMock()

    (
        replay_job_id,
        replay_context,
        replay_fingerprint,
    ) = await _consumer_dlq_replay_candidate_or_response(
        event_id="dlq-001",
        correlation_id="corr-001",
        dry_run=False,
        ingestion_job_service=ingestion_job_service,
        requested_by="ops",
    )

    assert replay_job_id == "job-001"
    assert replay_context is context
    assert len(replay_fingerprint) == 64
    ingestion_job_service.record_consumer_dlq_replay_audit.assert_not_awaited()
