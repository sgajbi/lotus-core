from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Any, Awaitable, Callable, Sequence, cast

from ..application import (
    ResolveTransactionReprocessingTargets,
    TransactionReprocessingTargetNotFound,
)
from ..DTOs.ingestion_job_dto import IngestionJobResponse
from ..ops_controls import enforce_ingestion_write_rate_limit
from ..ports.transaction_reprocessing import TransactionReprocessingTargetReadError
from ..request_metadata import create_ingestion_job_id, get_request_lineage
from .ingestion_job_service import IngestionJobService
from .ingestion_service import IngestionPublishError, IngestionService

logger = logging.getLogger(__name__)

HTTP_TOO_MANY_REQUESTS = 429
HTTP_CONFLICT = 409
HTTP_NOT_FOUND = 404
HTTP_SERVICE_UNAVAILABLE = 503

BatchPublisher = Callable[[Sequence[Any], str | None], Awaitable[None]]
SinglePublisher = Callable[[Any, str | None], Awaitable[None]]


class IngestionPublishCommandError(Exception):
    def __init__(self, status_code: int, detail: dict[str, Any]) -> None:
        super().__init__(str(detail.get("message", detail.get("code", "command failed"))))
        self.status_code = status_code
        self.detail = detail


class IngestionPublishUnavailable(Exception):
    def __init__(self, *, publish_error: IngestionPublishError, job_id: str | None = None) -> None:
        super().__init__(str(publish_error))
        self.publish_error = publish_error
        self.job_id = job_id


class IngestionPublishBookkeepingFailed(Exception):
    def __init__(self, *, job_id: str, published_record_count: int) -> None:
        super().__init__("Ingestion bookkeeping failed after publish.")
        self.job_id = job_id
        self.published_record_count = published_record_count
        self.failure_phase = "queue_bookkeeping"
        self.publish_state = "published"
        self.work_state = "published"


@dataclass(frozen=True, slots=True)
class BatchPublishIngestionCommand:
    endpoint: str
    entity_type: str
    records: Sequence[Any]
    idempotency_key: str | None
    request_payload: dict[str, Any]
    accepted_message: str


@dataclass(frozen=True, slots=True)
class PortfolioBundlePublishIngestionCommand:
    endpoint: str
    request: Any
    idempotency_key: str | None
    request_payload: dict[str, Any]
    accepted_count: int


@dataclass(frozen=True, slots=True)
class SinglePublishIngestionCommand:
    endpoint: str
    entity_type: str
    record: Any
    idempotency_key: str | None
    accepted_message: str


@dataclass(frozen=True, slots=True)
class IngestionCommandResult:
    message: str
    entity_type: str
    accepted_count: int
    idempotency_key: str | None
    job_id: str | None = None
    replayed: bool = False
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class IngestionPublishCommandHandler:
    ingestion_service: IngestionService
    ingestion_job_service: IngestionJobService
    resolve_transaction_reprocessing_targets: ResolveTransactionReprocessingTargets

    async def ingest_portfolios(
        self, command: BatchPublishIngestionCommand
    ) -> IngestionCommandResult:
        return await self.ingest_batch(command, self.publish_portfolios)

    async def ingest_instruments(
        self, command: BatchPublishIngestionCommand
    ) -> IngestionCommandResult:
        return await self.ingest_batch(command, self.publish_instruments)

    async def ingest_market_prices(
        self, command: BatchPublishIngestionCommand
    ) -> IngestionCommandResult:
        return await self.ingest_batch(command, self.publish_market_prices)

    async def ingest_fx_rates(
        self, command: BatchPublishIngestionCommand
    ) -> IngestionCommandResult:
        return await self.ingest_batch(command, self.publish_fx_rates)

    async def ingest_transactions(
        self, command: BatchPublishIngestionCommand
    ) -> IngestionCommandResult:
        return await self.ingest_batch(command, self.publish_transactions)

    async def ingest_reprocessing_requests(
        self, command: BatchPublishIngestionCommand
    ) -> IngestionCommandResult:
        await self._assert_ingestion_writable()
        await self._assert_reprocessing_publish_allowed(len(command.records))
        self._enforce_rate_limit(command.endpoint, len(command.records))
        replay_job = await self.ingestion_job_service.find_idempotent_job(
            endpoint=command.endpoint,
            idempotency_key=command.idempotency_key,
            request_payload=command.request_payload,
        )
        if replay_job is not None:
            return self._reprocessing_replay_result(command, replay_job)

        resolved_targets = await self._resolve_reprocessing_targets(command.records)
        job_result = await self._create_job(command)
        if not job_result.created:
            return self._reprocessing_replay_result(command, job_result.job)

        await self._publish_batch_or_mark_failed(
            replace(command, records=resolved_targets),
            job_result.job.job_id,
            self.publish_reprocessing_requests,
        )
        await self._mark_queued_or_raise(
            job_id=job_result.job.job_id,
            published_record_count=len(command.records),
        )
        return IngestionCommandResult(
            message=command.accepted_message,
            entity_type=command.entity_type,
            job_id=job_result.job.job_id,
            accepted_count=len(command.records),
            idempotency_key=command.idempotency_key,
        )

    @staticmethod
    def _reprocessing_replay_result(
        command: BatchPublishIngestionCommand,
        job: IngestionJobResponse,
    ) -> IngestionCommandResult:
        return IngestionCommandResult(
            message="Duplicate reprocessing request accepted via idempotency replay.",
            entity_type=command.entity_type,
            job_id=job.job_id,
            accepted_count=job.accepted_count,
            idempotency_key=command.idempotency_key,
            replayed=True,
        )

    async def ingest_portfolio_bundle(
        self, command: PortfolioBundlePublishIngestionCommand
    ) -> IngestionCommandResult:
        await self._assert_ingestion_writable()
        self._enforce_rate_limit(command.endpoint, command.accepted_count)
        job_result = await self._create_bundle_job(command)
        if not job_result.created:
            return IngestionCommandResult(
                message="Duplicate ingestion request accepted via idempotency replay.",
                entity_type="portfolio_bundle",
                job_id=job_result.job.job_id,
                accepted_count=job_result.job.accepted_count,
                idempotency_key=command.idempotency_key,
                replayed=True,
            )

        published_counts = await self._publish_bundle_or_mark_failed(
            command,
            job_result.job.job_id,
        )
        await self._mark_queued_or_raise(
            job_id=job_result.job.job_id,
            published_record_count=command.accepted_count,
        )
        return IngestionCommandResult(
            message=(
                "Portfolio bundle accepted for asynchronous ingestion processing. "
                f"Published counts: {published_counts}"
            ),
            entity_type="portfolio_bundle",
            job_id=job_result.job.job_id,
            accepted_count=command.accepted_count,
            idempotency_key=command.idempotency_key,
            metadata={"published_counts": published_counts},
        )

    async def ingest_transaction(
        self, command: SinglePublishIngestionCommand
    ) -> IngestionCommandResult:
        return await self.ingest_single(command, self.publish_transaction)

    async def ingest_batch(
        self,
        command: BatchPublishIngestionCommand,
        publisher: BatchPublisher,
    ) -> IngestionCommandResult:
        await self._assert_ingestion_writable()
        self._enforce_rate_limit(command.endpoint, len(command.records))
        job_result = await self._create_job(command)
        if not job_result.created:
            return IngestionCommandResult(
                message="Duplicate ingestion request accepted via idempotency replay.",
                entity_type=command.entity_type,
                job_id=job_result.job.job_id,
                accepted_count=job_result.job.accepted_count,
                idempotency_key=command.idempotency_key,
                replayed=True,
            )

        await self._publish_batch_or_mark_failed(command, job_result.job.job_id, publisher)
        await self._mark_queued_or_raise(
            job_id=job_result.job.job_id,
            published_record_count=len(command.records),
        )
        return IngestionCommandResult(
            message=command.accepted_message,
            entity_type=command.entity_type,
            job_id=job_result.job.job_id,
            accepted_count=len(command.records),
            idempotency_key=command.idempotency_key,
        )

    async def ingest_single(
        self,
        command: SinglePublishIngestionCommand,
        publisher: SinglePublisher,
    ) -> IngestionCommandResult:
        await self._assert_ingestion_writable()
        self._enforce_rate_limit(command.endpoint, 1)
        try:
            await publisher(command.record, command.idempotency_key)
        except IngestionPublishError as exc:
            raise IngestionPublishUnavailable(publish_error=exc) from exc

        return IngestionCommandResult(
            message=command.accepted_message,
            entity_type=command.entity_type,
            accepted_count=1,
            idempotency_key=command.idempotency_key,
        )

    async def publish_portfolios(self, records: Sequence[Any], idempotency_key: str | None) -> None:
        await self.ingestion_service.publish_portfolios(records, idempotency_key=idempotency_key)

    async def publish_instruments(
        self, records: Sequence[Any], idempotency_key: str | None
    ) -> None:
        await self.ingestion_service.publish_instruments(records, idempotency_key=idempotency_key)

    async def publish_market_prices(
        self, records: Sequence[Any], idempotency_key: str | None
    ) -> None:
        await self.ingestion_service.publish_market_prices(records, idempotency_key=idempotency_key)

    async def publish_fx_rates(self, records: Sequence[Any], idempotency_key: str | None) -> None:
        await self.ingestion_service.publish_fx_rates(records, idempotency_key=idempotency_key)

    async def publish_transactions(
        self, records: Sequence[Any], idempotency_key: str | None
    ) -> None:
        await self.ingestion_service.publish_transactions(records, idempotency_key=idempotency_key)

    async def publish_reprocessing_requests(
        self, records: Sequence[Any], idempotency_key: str | None
    ) -> None:
        await self.ingestion_service.publish_reprocessing_requests(
            list(records),
            idempotency_key=idempotency_key,
        )

    async def publish_transaction(self, record: Any, idempotency_key: str | None) -> None:
        await self.ingestion_service.publish_transaction(record, idempotency_key=idempotency_key)

    async def _assert_ingestion_writable(self) -> None:
        try:
            await self.ingestion_job_service.assert_ingestion_writable()
        except PermissionError as exc:
            raise IngestionPublishCommandError(
                HTTP_SERVICE_UNAVAILABLE,
                {"code": "INGESTION_MODE_BLOCKS_WRITES", "message": str(exc)},
            ) from exc

    async def _assert_reprocessing_publish_allowed(self, record_count: int) -> None:
        try:
            await self.ingestion_job_service.assert_reprocessing_publish_allowed(record_count)
        except PermissionError as exc:
            raise IngestionPublishCommandError(
                HTTP_CONFLICT,
                {"code": "INGESTION_REPLAY_BLOCKED", "message": str(exc)},
            ) from exc

    async def _resolve_reprocessing_targets(
        self,
        transaction_ids: Sequence[Any],
    ) -> Sequence[Any]:
        try:
            return await self.resolve_transaction_reprocessing_targets.execute(
                [str(transaction_id) for transaction_id in transaction_ids]
            )
        except TransactionReprocessingTargetNotFound as exc:
            raise IngestionPublishCommandError(
                HTTP_NOT_FOUND,
                {
                    "code": exc.reason_code,
                    **cast(dict[str, Any], exc.detail),
                },
            ) from exc
        except TransactionReprocessingTargetReadError as exc:
            raise IngestionPublishCommandError(
                HTTP_SERVICE_UNAVAILABLE,
                {
                    "code": "INGESTION_REPROCESSING_SOURCE_UNAVAILABLE",
                    "message": str(exc),
                },
            ) from exc

    @staticmethod
    def _enforce_rate_limit(endpoint: str, record_count: int) -> None:
        try:
            enforce_ingestion_write_rate_limit(endpoint=endpoint, record_count=record_count)
        except PermissionError as exc:
            raise IngestionPublishCommandError(
                HTTP_TOO_MANY_REQUESTS,
                {"code": "INGESTION_RATE_LIMIT_EXCEEDED", "message": str(exc)},
            ) from exc

    async def _create_job(self, command: BatchPublishIngestionCommand):
        correlation_id, request_id, trace_id = get_request_lineage()
        return await self.ingestion_job_service.create_or_get_job(
            job_id=create_ingestion_job_id(),
            endpoint=command.endpoint,
            entity_type=command.entity_type,
            accepted_count=len(command.records),
            idempotency_key=command.idempotency_key,
            correlation_id=correlation_id,
            request_id=request_id,
            trace_id=trace_id,
            request_payload=command.request_payload,
        )

    async def _create_bundle_job(self, command: PortfolioBundlePublishIngestionCommand):
        correlation_id, request_id, trace_id = get_request_lineage()
        return await self.ingestion_job_service.create_or_get_job(
            job_id=create_ingestion_job_id(),
            endpoint=command.endpoint,
            entity_type="portfolio_bundle",
            accepted_count=command.accepted_count,
            idempotency_key=command.idempotency_key,
            correlation_id=correlation_id,
            request_id=request_id,
            trace_id=trace_id,
            request_payload=command.request_payload,
        )

    async def _publish_batch_or_mark_failed(
        self,
        command: BatchPublishIngestionCommand,
        job_id: str,
        publisher: BatchPublisher,
    ) -> None:
        try:
            await publisher(command.records, command.idempotency_key)
        except IngestionPublishError as exc:
            await self.ingestion_job_service.mark_failed(
                job_id,
                str(exc),
                failed_record_keys=exc.failed_record_keys,
            )
            raise IngestionPublishUnavailable(publish_error=exc, job_id=job_id) from exc
        except Exception as exc:
            await self.ingestion_job_service.mark_failed(job_id, str(exc))
            raise

    async def _publish_bundle_or_mark_failed(
        self,
        command: PortfolioBundlePublishIngestionCommand,
        job_id: str,
    ) -> dict[str, int]:
        try:
            return cast(
                dict[str, int],
                await self.ingestion_service.publish_portfolio_bundle(
                    command.request,
                    idempotency_key=command.idempotency_key,
                ),
            )
        except IngestionPublishError as exc:
            await self.ingestion_job_service.mark_failed(
                job_id,
                str(exc),
                failed_record_keys=exc.failed_record_keys,
            )
            raise IngestionPublishUnavailable(publish_error=exc, job_id=job_id) from exc
        except Exception as exc:
            await self.ingestion_job_service.mark_failed(job_id, str(exc))
            raise

    async def _mark_queued_or_raise(self, *, job_id: str, published_record_count: int) -> None:
        try:
            queued = await self.ingestion_job_service.mark_queued(job_id)
        except Exception as exc:
            await self._record_bookkeeping_failure(job_id=job_id, failure_reason=str(exc))
            raise IngestionPublishBookkeepingFailed(
                job_id=job_id,
                published_record_count=published_record_count,
            ) from exc

        if not queued:
            await self._record_bookkeeping_failure(
                job_id=job_id,
                failure_reason="job queue transition was rejected",
            )
            raise IngestionPublishBookkeepingFailed(
                job_id=job_id,
                published_record_count=published_record_count,
            )

    async def _record_bookkeeping_failure(self, *, job_id: str, failure_reason: str) -> None:
        try:
            await self.ingestion_job_service.record_failure_observation(
                job_id,
                failure_reason,
                failure_phase="queue_bookkeeping",
            )
        except Exception:
            logger.exception(
                "Failed to persist ingestion bookkeeping failure observation.",
                extra={"job_id": job_id, "failure_phase": "queue_bookkeeping"},
            )
