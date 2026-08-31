from functools import partial
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.ingestion_service.app.application import (
    TransactionReprocessingTargetNotFound,
)
from src.services.ingestion_service.app.domain import TransactionReprocessingTarget
from src.services.ingestion_service.app.DTOs.corporate_action_manifest_dto import (
    CorporateActionManifestIngestionRequest,
)
from src.services.ingestion_service.app.DTOs.fixed_income_book_cost_authority_dto import (
    FixedIncomeBookCostAuthorityIngestionRequest,
)
from src.services.ingestion_service.app.ports.transaction_reprocessing import (
    TransactionReprocessingTargetReadError,
)
from src.services.ingestion_service.app.services import ingestion_publish_commands
from src.services.ingestion_service.app.services.ingestion_publish_commands import (
    BatchPublishIngestionCommand as BatchPublishIngestionCommandContract,
)
from src.services.ingestion_service.app.services.ingestion_publish_commands import (
    IngestionPublishBookkeepingFailed,
    IngestionPublishCommandError,
    IngestionPublishCommandHandler,
    IngestionPublishUnavailable,
    SinglePublishIngestionCommand,
)
from src.services.ingestion_service.app.services.ingestion_service import IngestionPublishError
from tests.test_support.tenant import TEST_TENANT_CONTEXT, TEST_TENANT_ID

BatchPublishIngestionCommand = partial(
    BatchPublishIngestionCommandContract,
    tenant_context=TEST_TENANT_CONTEXT,
)


def _job_result(
    *,
    created: bool = True,
    job_id: str = "job-1",
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


def _handler() -> IngestionPublishCommandHandler:
    ingestion_service = SimpleNamespace()
    job_service = SimpleNamespace(
        assert_ingestion_writable=AsyncMock(),
        assert_reprocessing_publish_allowed=AsyncMock(),
        create_or_get_job=AsyncMock(return_value=_job_result()),
        find_idempotent_job=AsyncMock(return_value=None),
        mark_failed=AsyncMock(),
        mark_queued=AsyncMock(return_value=True),
        record_failure_observation=AsyncMock(),
    )
    return IngestionPublishCommandHandler(
        ingestion_service=ingestion_service,
        ingestion_job_service=job_service,
        idempotency_replay_reader=SimpleNamespace(find_matching_job=AsyncMock(return_value=None)),
        resolve_transaction_reprocessing_targets=SimpleNamespace(
            execute=AsyncMock(
                side_effect=lambda transaction_ids: tuple(
                    TransactionReprocessingTarget(
                        transaction_id=transaction_id,
                        portfolio_id=f"PORT-{transaction_id}",
                    )
                    for transaction_id in transaction_ids
                )
            )
        ),
    )


def _fixed_income_request() -> FixedIncomeBookCostAuthorityIngestionRequest:
    return FixedIncomeBookCostAuthorityIngestionRequest.model_validate(
        {
            "authorities": [
                {
                    "authority_type": "POLICY_ASSIGNMENT",
                    "header": {
                        "scope": {
                            "tenant_id": "TENANT_SG",
                            "legal_book_id": "BOOK_SG_PB",
                            "portfolio_id": "PORTFOLIO_001",
                            "security_id": "BOND_001",
                            "lot_id": "LOT_001",
                        },
                        "source": {
                            "source_system": "accounting-policy-master",
                            "source_record_id": "assignment-001",
                            "source_revision": "revision-1",
                            "source_version": 1,
                            "observed_at": "2026-08-03T09:00:00+08:00",
                        },
                        "status": "ACTIVE",
                        "valid_from": "2026-08-01",
                    },
                    "policy_id": "IFRS9_EIR_LOCAL",
                    "policy_version": 1,
                    "assignment_reason": "Approved accounting treatment",
                }
            ]
        }
    )


def _corporate_action_manifest_request() -> CorporateActionManifestIngestionRequest:
    return CorporateActionManifestIngestionRequest.model_validate(
        {
            "manifests": [
                {
                    "corporate_action_event_id": "EVENT_001",
                    "tenant_id": "TENANT_SG",
                    "legal_book_id": "BOOK_SG_PB",
                    "portfolio_id": "PORTFOLIO_001",
                    "linked_transaction_group_id": "GROUP_001",
                    "parent_event_reference": "PARENT_001",
                    "corporate_action_type": "SPIN_OFF",
                    "version": 1,
                    "completion_declared": False,
                    "expected_children": [],
                    "source": {
                        "source_system": "corporate-actions-master",
                        "source_record_id": "EVENT_001",
                        "source_revision": "revision-1",
                        "source_content_hash": "a" * 64,
                        "observed_at": "2026-08-11T02:15:00Z",
                    },
                }
            ]
        }
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
    handler.ingestion_job_service.mark_queued.assert_awaited_once_with(
        "job-1",
        tenant_id=TEST_TENANT_ID,
    )
    handler.ingestion_job_service.mark_failed.assert_not_awaited()
    assert (
        handler.ingestion_job_service.create_or_get_job.await_args.kwargs["tenant_context"]
        is TEST_TENANT_CONTEXT
    )


@pytest.mark.asyncio
async def test_fixed_income_authority_command_rebuilds_typed_batch_for_publication() -> None:
    handler = _handler()
    handler.ingestion_service.publish_fixed_income_book_cost_authorities = AsyncMock()
    request = _fixed_income_request()

    result = await handler.ingest_fixed_income_book_cost_authorities(
        BatchPublishIngestionCommand(
            endpoint="/ingest/fixed-income-book-cost-authorities",
            entity_type="fixed_income_book_cost_authority",
            records=request.authorities,
            idempotency_key="book-cost-001",
            request_payload=request.model_dump(mode="json"),
            accepted_message="Accepted.",
        )
    )

    published_request = (
        handler.ingestion_service.publish_fixed_income_book_cost_authorities.await_args.args[0]
    )
    assert isinstance(published_request, FixedIncomeBookCostAuthorityIngestionRequest)
    assert published_request == request
    assert (
        handler.ingestion_service.publish_fixed_income_book_cost_authorities.await_args.kwargs[
            "idempotency_key"
        ]
        == "book-cost-001"
    )
    assert result.entity_type == "fixed_income_book_cost_authority"
    assert result.accepted_count == 1


@pytest.mark.asyncio
async def test_manifest_command_rebuilds_typed_batch_for_publication() -> None:
    handler = _handler()
    handler.ingestion_service.publish_corporate_action_manifests = AsyncMock()
    request = _corporate_action_manifest_request()

    result = await handler.ingest_corporate_action_manifests(
        BatchPublishIngestionCommand(
            endpoint="/ingest/corporate-action-manifests",
            entity_type="corporate_action_manifest",
            records=request.manifests,
            idempotency_key="manifest-001",
            request_payload=request.model_dump(mode="json"),
            accepted_message="Accepted.",
        )
    )

    publish_call = handler.ingestion_service.publish_corporate_action_manifests.await_args
    published_request = publish_call.args[0]
    assert isinstance(published_request, CorporateActionManifestIngestionRequest)
    assert published_request == request
    assert result.entity_type == "corporate_action_manifest"
    assert result.accepted_count == 1


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
async def test_durable_batch_replay_bypasses_write_controls() -> None:
    handler = _handler()
    handler.idempotency_replay_reader.find_matching_job.return_value = SimpleNamespace(
        job_id="job-replay",
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
    handler.ingestion_job_service.assert_ingestion_writable.assert_not_awaited()
    handler.ingestion_job_service.create_or_get_job.assert_not_awaited()
    publisher.assert_not_awaited()


@pytest.mark.asyncio
async def test_batch_publish_command_replays_original_publish_failure() -> None:
    handler = _handler()
    handler.ingestion_job_service.create_or_get_job.return_value = _job_result(
        created=False,
        job_id="job-failed-replay",
        status="failed",
        failure_reason="broker timeout",
        failure_status_code=503,
        failure_code="INGESTION_PUBLISH_FAILED",
        failure_detail={
            "message": "broker timeout",
            "dependency": "kafka",
            "retryable": True,
            "failed_record_keys": ["T1"],
        },
        failure_headers={"Retry-After": "30"},
    )
    publisher = AsyncMock()

    with pytest.raises(IngestionPublishCommandError) as exc_info:
        await handler.ingest_batch(
            BatchPublishIngestionCommand(
                endpoint="/ingest/transactions",
                entity_type="transaction",
                records=[{"transaction_id": "T1"}],
                idempotency_key="idem-failed-replay",
                request_payload={"transactions": [{"transaction_id": "T1"}]},
                accepted_message="Transactions accepted.",
            ),
            publisher,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["code"] == "INGESTION_PUBLISH_FAILED"
    assert exc_info.value.detail["job_id"] == "job-failed-replay"
    assert exc_info.value.headers == {"Retry-After": "30"}
    publisher.assert_not_awaited()


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
        "Ingestion publishing failed before durable queue confirmation.",
        tenant_id=TEST_TENANT_ID,
        failed_record_keys=["T1"],
        failure_status_code=503,
        failure_code="INGESTION_PUBLISH_FAILED",
        failure_detail={
            "code": "INGESTION_PUBLISH_FAILED",
            "message": "Ingestion publishing failed before durable queue confirmation.",
            "dependency": "kafka",
            "retryable": True,
            "retry_after_seconds": 30,
            "publish_state": "unpublished",
            "published_record_count": 0,
            "failed_record_keys": ["T1"],
            "job_id": "job-1",
        },
        failure_headers={"Retry-After": "30"},
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
    assert exc_info.value.detail["code"] == "INGESTION_JOB_BOOKKEEPING_FAILED"
    assert exc_info.value.detail["publish_state"] == "published"
    handler.ingestion_job_service.record_failure_observation.assert_awaited_once_with(
        "job-1",
        "job queue transition was rejected",
        failure_phase="queue_bookkeeping",
        failure_status_code=500,
        failure_code="INGESTION_JOB_BOOKKEEPING_FAILED",
        failure_detail=exc_info.value.detail,
    )


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

    async def resolve_reprocessing_targets(transaction_ids):
        events.append(f"resolve:{','.join(transaction_ids)}")
        return tuple(
            TransactionReprocessingTarget(
                transaction_id=transaction_id,
                portfolio_id=f"PORT-{transaction_id}",
            )
            for transaction_id in transaction_ids
        )

    handler.ingestion_job_service.assert_ingestion_writable.side_effect = writable
    handler.ingestion_job_service.assert_reprocessing_publish_allowed.side_effect = (
        reprocessing_allowed
    )
    handler.ingestion_service.publish_reprocessing_requests = AsyncMock(
        side_effect=publish_reprocessing_requests
    )
    handler.resolve_transaction_reprocessing_targets.execute.side_effect = (
        resolve_reprocessing_targets
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
        "resolve:T1,T2",
        "publish:2:idem-reprocess",
    ]


@pytest.mark.asyncio
async def test_reprocessing_replay_does_not_require_source_resolution() -> None:
    handler = _handler()
    handler.ingestion_service.publish_reprocessing_requests = AsyncMock()
    handler.idempotency_replay_reader.find_matching_job.return_value = SimpleNamespace(
        job_id="job-replay",
        accepted_count=2,
        status="queued",
        failure_reason=None,
        failure_status_code=None,
        failure_code=None,
        failure_detail=None,
        failure_headers=None,
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

    assert result.replayed is True
    assert result.job_id == "job-replay"
    handler.resolve_transaction_reprocessing_targets.execute.assert_not_awaited()
    handler.ingestion_job_service.create_or_get_job.assert_not_awaited()
    handler.ingestion_service.publish_reprocessing_requests.assert_not_awaited()
    handler.ingestion_job_service.assert_ingestion_writable.assert_not_awaited()
    handler.ingestion_job_service.assert_reprocessing_publish_allowed.assert_not_awaited()


@pytest.mark.asyncio
async def test_reprocessing_replay_reproduces_original_failure_before_source_resolution() -> None:
    handler = _handler()
    handler.ingestion_service.publish_reprocessing_requests = AsyncMock()
    handler.idempotency_replay_reader.find_matching_job.return_value = SimpleNamespace(
        job_id="job-failed-replay",
        accepted_count=2,
        status="failed",
        failure_reason="broker timeout",
        failure_status_code=503,
        failure_code="INGESTION_PUBLISH_FAILED",
        failure_detail={
            "message": "broker timeout",
            "dependency": "kafka",
            "failed_record_keys": ["T1", "T2"],
        },
        failure_headers={"Retry-After": "30"},
    )

    with pytest.raises(IngestionPublishCommandError) as exc_info:
        await handler.ingest_reprocessing_requests(
            BatchPublishIngestionCommand(
                endpoint="/reprocess/transactions",
                entity_type="reprocessing_request",
                records=["T1", "T2"],
                idempotency_key="idem-reprocess",
                request_payload={"transaction_ids": ["T1", "T2"]},
                accepted_message="Reprocessing accepted.",
            )
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["code"] == "INGESTION_PUBLISH_FAILED"
    assert exc_info.value.detail["job_id"] == "job-failed-replay"
    assert exc_info.value.headers == {"Retry-After": "30"}
    handler.resolve_transaction_reprocessing_targets.execute.assert_not_awaited()
    handler.ingestion_job_service.create_or_get_job.assert_not_awaited()
    handler.ingestion_service.publish_reprocessing_requests.assert_not_awaited()


@pytest.mark.asyncio
async def test_reprocessing_command_rejects_missing_source_before_job_creation() -> None:
    handler = _handler()
    handler.resolve_transaction_reprocessing_targets.execute.side_effect = (
        TransactionReprocessingTargetNotFound(["TXN-404"])
    )

    with pytest.raises(IngestionPublishCommandError) as exc_info:
        await handler.ingest_reprocessing_requests(
            BatchPublishIngestionCommand(
                endpoint="/reprocess/transactions",
                entity_type="reprocessing_request",
                records=["TXN-404"],
                idempotency_key=None,
                request_payload={"transaction_ids": ["TXN-404"]},
                accepted_message="Reprocessing accepted.",
            )
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "INGESTION_REPROCESSING_SOURCE_NOT_FOUND"
    assert exc_info.value.detail["missing_transaction_ids"] == ["TXN-404"]
    handler.ingestion_job_service.create_or_get_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_reprocessing_command_maps_source_dependency_failure() -> None:
    handler = _handler()
    handler.resolve_transaction_reprocessing_targets.execute.side_effect = (
        TransactionReprocessingTargetReadError(
            "Transaction reprocessing source lookup is unavailable."
        )
    )

    with pytest.raises(IngestionPublishCommandError) as exc_info:
        await handler.ingest_reprocessing_requests(
            BatchPublishIngestionCommand(
                endpoint="/reprocess/transactions",
                entity_type="reprocessing_request",
                records=["TXN-1"],
                idempotency_key=None,
                request_payload={"transaction_ids": ["TXN-1"]},
                accepted_message="Reprocessing accepted.",
            )
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == {
        "code": "INGESTION_REPROCESSING_SOURCE_UNAVAILABLE",
        "message": "Transaction reprocessing source lookup is unavailable.",
    }
    handler.ingestion_job_service.create_or_get_job.assert_not_awaited()
