from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.ingestion_service.app.services import ingestion_publish_commands
from src.services.ingestion_service.app.services.ingestion_publish_commands import (
    BatchPublishIngestionCommand,
    IngestionPublishBookkeepingFailed,
    IngestionPublishCommandError,
    IngestionPublishCommandHandler,
    IngestionPublishUnavailable,
    SinglePublishIngestionCommand,
)
from src.services.ingestion_service.app.services.ingestion_service import IngestionPublishError


def _job_result(*, created: bool = True, job_id: str = "job-1", accepted_count: int = 2):
    return SimpleNamespace(
        created=created,
        job=SimpleNamespace(job_id=job_id, accepted_count=accepted_count),
    )


def _handler() -> IngestionPublishCommandHandler:
    ingestion_service = SimpleNamespace()
    job_service = SimpleNamespace(
        assert_ingestion_writable=AsyncMock(),
        assert_reprocessing_publish_allowed=AsyncMock(),
        create_or_get_job=AsyncMock(return_value=_job_result()),
        mark_failed=AsyncMock(),
        mark_queued=AsyncMock(return_value=True),
        record_failure_observation=AsyncMock(),
    )
    return IngestionPublishCommandHandler(
        ingestion_service=ingestion_service,
        ingestion_job_service=job_service,
    )


@pytest.mark.asyncio
async def test_batch_publish_command_creates_job_publishes_and_marks_queued() -> None:
    handler = _handler()
    publisher = AsyncMock()

    result = await handler.ingest_batch(
        BatchPublishIngestionCommand(
            endpoint="/ingest/portfolios",
            entity_type="portfolio",
            records=[{"portfolio_id": "P1"}, {"portfolio_id": "P2"}],
            idempotency_key="idem-1",
            request_payload={"portfolios": [{"portfolio_id": "P1"}]},
            accepted_message="Portfolios accepted.",
        ),
        publisher,
    )

    assert result.job_id == "job-1"
    assert result.accepted_count == 2
    publisher.assert_awaited_once()
    handler.ingestion_job_service.mark_queued.assert_awaited_once_with("job-1")
    handler.ingestion_job_service.mark_failed.assert_not_awaited()


@pytest.mark.asyncio
async def test_batch_publish_command_returns_replay_without_publish() -> None:
    handler = _handler()
    handler.ingestion_job_service.create_or_get_job.return_value = _job_result(
        created=False,
        job_id="job-replay",
        accepted_count=3,
    )
    publisher = AsyncMock()

    result = await handler.ingest_batch(
        BatchPublishIngestionCommand(
            endpoint="/ingest/transactions",
            entity_type="transaction",
            records=[{"transaction_id": "T1"}],
            idempotency_key="idem-replay",
            request_payload={"transactions": [{"transaction_id": "T1"}]},
            accepted_message="Transactions accepted.",
        ),
        publisher,
    )

    assert result.replayed is True
    assert result.job_id == "job-replay"
    assert result.accepted_count == 3
    publisher.assert_not_awaited()
    handler.ingestion_job_service.mark_queued.assert_not_awaited()


@pytest.mark.asyncio
async def test_batch_publish_command_marks_failed_on_publish_error() -> None:
    handler = _handler()
    publish_error = IngestionPublishError("broker timeout", ["T1"], published_record_count=0)
    publisher = AsyncMock(side_effect=publish_error)

    with pytest.raises(IngestionPublishUnavailable) as exc_info:
        await handler.ingest_batch(
            BatchPublishIngestionCommand(
                endpoint="/ingest/transactions",
                entity_type="transaction",
                records=[{"transaction_id": "T1"}],
                idempotency_key="idem-1",
                request_payload={"transactions": [{"transaction_id": "T1"}]},
                accepted_message="Transactions accepted.",
            ),
            publisher,
        )

    assert exc_info.value.job_id == "job-1"
    assert exc_info.value.publish_error is publish_error
    handler.ingestion_job_service.mark_failed.assert_awaited_once_with(
        "job-1",
        "broker timeout",
        failed_record_keys=["T1"],
    )


@pytest.mark.asyncio
async def test_batch_publish_command_raises_bookkeeping_failure_when_queue_rejected() -> None:
    handler = _handler()
    handler.ingestion_job_service.mark_queued.return_value = False

    with pytest.raises(IngestionPublishBookkeepingFailed) as exc_info:
        await handler.ingest_batch(
            BatchPublishIngestionCommand(
                endpoint="/ingest/fx-rates",
                entity_type="fx_rate",
                records=[{"rate": "1.0"}],
                idempotency_key=None,
                request_payload={"fx_rates": [{"rate": "1.0"}]},
                accepted_message="FX accepted.",
            ),
            AsyncMock(),
        )

    assert exc_info.value.job_id == "job-1"
    assert exc_info.value.published_record_count == 1
    handler.ingestion_job_service.record_failure_observation.assert_awaited_once()


@pytest.mark.asyncio
async def test_single_publish_command_has_no_job_lifecycle() -> None:
    handler = _handler()
    publisher = AsyncMock()

    result = await handler.ingest_single(
        SinglePublishIngestionCommand(
            endpoint="/ingest/transaction",
            entity_type="transaction",
            record={"transaction_id": "T1"},
            idempotency_key="single-key",
            accepted_message="Transaction accepted.",
        ),
        publisher,
    )

    assert result.job_id is None
    assert result.accepted_count == 1
    publisher.assert_awaited_once_with({"transaction_id": "T1"}, "single-key")
    handler.ingestion_job_service.create_or_get_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_command_error_maps_blocked_mode_without_router_logic() -> None:
    handler = _handler()
    handler.ingestion_job_service.assert_ingestion_writable.side_effect = PermissionError(
        "writes disabled"
    )

    with pytest.raises(IngestionPublishCommandError) as exc_info:
        await handler.ingest_single(
            SinglePublishIngestionCommand(
                endpoint="/ingest/transaction",
                entity_type="transaction",
                record={"transaction_id": "T1"},
                idempotency_key=None,
                accepted_message="Transaction accepted.",
            ),
            AsyncMock(),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == {
        "code": "INGESTION_MODE_BLOCKS_WRITES",
        "message": "writes disabled",
    }


@pytest.mark.asyncio
async def test_reprocessing_command_preserves_policy_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = _handler()
    events: list[str] = []

    async def writable() -> None:
        events.append("writable")

    async def reprocessing_allowed(record_count: int) -> None:
        events.append(f"policy:{record_count}")

    def rate_limit(endpoint: str, record_count: int) -> None:
        events.append(f"rate:{endpoint}:{record_count}")

    async def publish_reprocessing_requests(records, *, idempotency_key):
        events.append(f"publish:{len(records)}:{idempotency_key}")

    handler.ingestion_job_service.assert_ingestion_writable.side_effect = writable
    handler.ingestion_job_service.assert_reprocessing_publish_allowed.side_effect = (
        reprocessing_allowed
    )
    handler.ingestion_service.publish_reprocessing_requests = AsyncMock(
        side_effect=publish_reprocessing_requests
    )
    monkeypatch.setattr(
        ingestion_publish_commands,
        "enforce_ingestion_write_rate_limit",
        rate_limit,
    )

    result = await handler.ingest_reprocessing_requests(
        BatchPublishIngestionCommand(
            endpoint="/reprocess/transactions",
            entity_type="reprocessing_request",
            records=["T1", "T2"],
            idempotency_key="idem-reprocess",
            request_payload={"transaction_ids": ["T1", "T2"]},
            accepted_message="Reprocessing accepted.",
        )
    )

    assert result.message == "Reprocessing accepted."
    assert events == [
        "writable",
        "policy:2",
        "rate:/reprocess/transactions:2",
        "publish:2:idem-reprocess",
    ]
