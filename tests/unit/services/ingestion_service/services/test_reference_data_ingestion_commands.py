from functools import partial
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from portfolio_common.domain.valuation.assignments import ValuationPolicyAssignmentError
from portfolio_common.domain.valuation.source_facts import MarketPriceSourceFactError

from src.services.ingestion_service.app.services.reference_data_ingestion_commands import (
    ReferenceDataBookkeepingFailed,
    ReferenceDataIngestionCommandError,
    ReferenceDataIngestionCommandHandler,
)
from src.services.ingestion_service.app.services.reference_data_ingestion_commands import (
    ReferenceDataIngestionCommand as ReferenceDataIngestionCommandContract,
)
from tests.test_support.tenant import TEST_TENANT_CONTEXT

ReferenceDataIngestionCommand = partial(
    ReferenceDataIngestionCommandContract,
    tenant_context=TEST_TENANT_CONTEXT,
)


def _job_result(
    *,
    created: bool = True,
    job_id: str = "ref-job-1",
    accepted_count: int = 2,
    status: str | None = None,
    failure_reason: str | None = None,
    failure_status_code: int | None = None,
    failure_code: str | None = None,
    failure_detail: dict | None = None,
    failure_headers: dict[str, str] | None = None,
):
    return SimpleNamespace(
        created=created,
        job=SimpleNamespace(
            job_id=job_id,
            accepted_count=accepted_count,
            status=status or ("accepted" if created else "queued"),
            failure_reason=failure_reason,
            failure_status_code=failure_status_code,
            failure_code=failure_code,
            failure_detail=failure_detail,
            failure_headers=failure_headers,
        ),
    )


def _registry_command(*, persist_side_effect=None):
    command = SimpleNamespace(
        endpoint="/ingest/reference",
        entity_type="reference_data",
        accepted_count=lambda request: len(request.records),
        request_payload=lambda request: {"records": request.records},
        persist=AsyncMock(side_effect=persist_side_effect),
    )
    return command


def _handler() -> ReferenceDataIngestionCommandHandler:
    reference_data_service = SimpleNamespace()
    job_service = SimpleNamespace(
        assert_ingestion_writable=AsyncMock(),
        create_or_get_job=AsyncMock(return_value=_job_result()),
        mark_failed=AsyncMock(),
        mark_queued=AsyncMock(return_value=True),
        record_failure_observation=AsyncMock(),
    )
    return ReferenceDataIngestionCommandHandler(
        reference_data_service=reference_data_service,
        ingestion_job_service=job_service,
        idempotency_replay_reader=SimpleNamespace(find_matching_job=AsyncMock(return_value=None)),
    )


@pytest.mark.asyncio
async def test_reference_data_command_persists_and_marks_queued() -> None:
    handler = _handler()
    registry_command = _registry_command()
    request = SimpleNamespace(records=[{"id": "R1"}, {"id": "R2"}])

    result = await handler.ingest_reference_data(
        ReferenceDataIngestionCommand(
            endpoint="/ingest/reference",
            idempotency_key="ref-key",
            registry_command=registry_command,
            request=request,
        )
    )

    assert result.job_id == "ref-job-1"
    assert result.accepted_count == 2
    registry_command.persist.assert_awaited_once_with(handler.reference_data_service, request)
    handler.ingestion_job_service.mark_queued.assert_awaited_once_with("ref-job-1")
    assert (
        handler.ingestion_job_service.create_or_get_job.await_args.kwargs["tenant_context"]
        is TEST_TENANT_CONTEXT
    )


@pytest.mark.asyncio
async def test_reference_data_command_replay_skips_persist() -> None:
    handler = _handler()
    handler.ingestion_job_service.create_or_get_job.return_value = _job_result(
        created=False,
        job_id="ref-job-replay",
        accepted_count=3,
    )
    registry_command = _registry_command()

    result = await handler.ingest_reference_data(
        ReferenceDataIngestionCommand(
            endpoint="/ingest/reference",
            idempotency_key="ref-replay",
            registry_command=registry_command,
            request=SimpleNamespace(records=[{"id": "R1"}]),
        )
    )

    assert result.replayed is True
    assert result.job_id == "ref-job-replay"
    assert result.accepted_count == 3
    registry_command.persist.assert_not_awaited()
    handler.ingestion_job_service.mark_queued.assert_not_awaited()


@pytest.mark.asyncio
async def test_reference_data_replay_bypasses_write_controls() -> None:
    handler = _handler()
    handler.idempotency_replay_reader.find_matching_job.return_value = SimpleNamespace(
        job_id="ref-job-replay",
        accepted_count=1,
        status="queued",
        failure_reason=None,
        failure_status_code=None,
        failure_code=None,
        failure_detail=None,
        failure_headers=None,
    )
    handler.ingestion_job_service.assert_ingestion_writable.side_effect = PermissionError(
        "writes disabled"
    )
    registry_command = _registry_command()

    result = await handler.ingest_reference_data(
        ReferenceDataIngestionCommand(
            endpoint="/ingest/reference",
            idempotency_key="ref-replay",
            registry_command=registry_command,
            request=SimpleNamespace(records=[{"id": "R1"}]),
        )
    )

    assert result.replayed is True
    handler.ingestion_job_service.assert_ingestion_writable.assert_not_awaited()
    handler.ingestion_job_service.create_or_get_job.assert_not_awaited()
    registry_command.persist.assert_not_awaited()


@pytest.mark.asyncio
async def test_reference_data_command_replays_original_failed_outcome() -> None:
    handler = _handler()
    handler.ingestion_job_service.create_or_get_job.return_value = _job_result(
        created=False,
        job_id="ref-job-failed",
        status="failed",
        failure_reason="competing exact price authority",
        failure_status_code=409,
        failure_code="MARKET_PRICE_SOURCE_FACT_CONFLICT",
        failure_detail={
            "message": "competing exact price authority",
            "job_id": "ref-job-failed",
        },
    )
    registry_command = _registry_command()

    with pytest.raises(ReferenceDataIngestionCommandError) as exc_info:
        await handler.ingest_reference_data(
            ReferenceDataIngestionCommand(
                endpoint="/ingest/authoritative-market-price-source-facts",
                idempotency_key="ref-failed-replay",
                registry_command=registry_command,
                request=SimpleNamespace(records=[{"id": "R1"}]),
            )
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {
        "code": "MARKET_PRICE_SOURCE_FACT_CONFLICT",
        "message": (
            "Authoritative market-price source evidence conflicts with persisted authority."
        ),
        "job_id": "ref-job-failed",
    }
    registry_command.persist.assert_not_awaited()


@pytest.mark.asyncio
async def test_reference_data_command_does_not_claim_unresolved_job_succeeded() -> None:
    handler = _handler()
    handler.ingestion_job_service.create_or_get_job.return_value = _job_result(
        created=False,
        job_id="ref-job-in-progress",
        status="accepted",
    )
    registry_command = _registry_command()

    with pytest.raises(ReferenceDataIngestionCommandError) as exc_info:
        await handler.ingest_reference_data(
            ReferenceDataIngestionCommand(
                endpoint="/ingest/reference",
                idempotency_key="ref-in-progress",
                registry_command=registry_command,
                request=SimpleNamespace(records=[{"id": "R1"}]),
            )
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "INGESTION_REQUEST_IN_PROGRESS"
    assert exc_info.value.detail["job_id"] == "ref-job-in-progress"
    registry_command.persist.assert_not_awaited()


@pytest.mark.asyncio
async def test_reference_data_command_marks_failed_on_persist_error() -> None:
    handler = _handler()
    registry_command = _registry_command(persist_side_effect=RuntimeError("db unavailable"))

    with pytest.raises(ReferenceDataIngestionCommandError) as exc_info:
        await handler.ingest_reference_data(
            ReferenceDataIngestionCommand(
                endpoint="/ingest/reference",
                idempotency_key=None,
                registry_command=registry_command,
                request=SimpleNamespace(records=[{"id": "R1"}]),
            )
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {
        "code": "REFERENCE_DATA_PERSIST_FAILED",
        "message": "Reference-data persistence failed.",
        "job_id": "ref-job-1",
    }
    handler.ingestion_job_service.mark_failed.assert_awaited_once_with(
        "ref-job-1",
        "Reference-data persistence failed.",
        failure_phase="persist",
        failure_status_code=500,
        failure_code="REFERENCE_DATA_PERSIST_FAILED",
        failure_detail={
            "code": "REFERENCE_DATA_PERSIST_FAILED",
            "message": "Reference-data persistence failed.",
            "job_id": "ref-job-1",
        },
    )


@pytest.mark.asyncio
async def test_reference_data_command_maps_valuation_authority_conflict_to_409() -> None:
    handler = _handler()
    registry_command = _registry_command(
        persist_side_effect=ValuationPolicyAssignmentError("overlapping valuation authority")
    )

    with pytest.raises(ReferenceDataIngestionCommandError) as exc_info:
        await handler.ingest_reference_data(
            ReferenceDataIngestionCommand(
                endpoint="/ingest/instrument-valuation-policy-assignments",
                idempotency_key="valuation-policy-conflict",
                registry_command=registry_command,
                request=SimpleNamespace(records=[{"id": "R1"}]),
            )
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {
        "code": "VALUATION_POLICY_ASSIGNMENT_CONFLICT",
        "message": ("Valuation-policy assignment evidence conflicts with persisted authority."),
        "job_id": "ref-job-1",
    }
    handler.ingestion_job_service.mark_failed.assert_awaited_once_with(
        "ref-job-1",
        "Valuation-policy assignment evidence conflicts with persisted authority.",
        failure_phase="persist",
        failure_status_code=409,
        failure_code="VALUATION_POLICY_ASSIGNMENT_CONFLICT",
        failure_detail={
            "code": "VALUATION_POLICY_ASSIGNMENT_CONFLICT",
            "message": ("Valuation-policy assignment evidence conflicts with persisted authority."),
            "job_id": "ref-job-1",
        },
    )


@pytest.mark.asyncio
async def test_reference_data_command_maps_market_price_authority_conflict_to_409() -> None:
    handler = _handler()
    registry_command = _registry_command(
        persist_side_effect=MarketPriceSourceFactError("competing exact price authority")
    )

    with pytest.raises(ReferenceDataIngestionCommandError) as exc_info:
        await handler.ingest_reference_data(
            ReferenceDataIngestionCommand(
                endpoint="/ingest/authoritative-market-price-source-facts",
                idempotency_key="market-price-authority-conflict",
                registry_command=registry_command,
                request=SimpleNamespace(records=[{"id": "R1"}]),
            )
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {
        "code": "MARKET_PRICE_SOURCE_FACT_CONFLICT",
        "message": (
            "Authoritative market-price source evidence conflicts with persisted authority."
        ),
        "job_id": "ref-job-1",
    }
    handler.ingestion_job_service.mark_failed.assert_awaited_once_with(
        "ref-job-1",
        "Authoritative market-price source evidence conflicts with persisted authority.",
        failure_phase="persist",
        failure_status_code=409,
        failure_code="MARKET_PRICE_SOURCE_FACT_CONFLICT",
        failure_detail={
            "code": "MARKET_PRICE_SOURCE_FACT_CONFLICT",
            "message": (
                "Authoritative market-price source evidence conflicts with persisted authority."
            ),
            "job_id": "ref-job-1",
        },
    )


@pytest.mark.asyncio
async def test_reference_data_command_raises_bookkeeping_failure_when_queue_rejected() -> None:
    handler = _handler()
    handler.ingestion_job_service.mark_queued.return_value = False

    with pytest.raises(ReferenceDataBookkeepingFailed) as exc_info:
        await handler.ingest_reference_data(
            ReferenceDataIngestionCommand(
                endpoint="/ingest/reference",
                idempotency_key=None,
                registry_command=_registry_command(),
                request=SimpleNamespace(records=[{"id": "R1"}]),
            )
        )

    assert exc_info.value.job_id == "ref-job-1"
    handler.ingestion_job_service.record_failure_observation.assert_awaited_once()
