from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from portfolio_common.db import get_async_db_session
from portfolio_common.monitoring import INGESTION_BACKLOG_AGE_SECONDS, INGESTION_MODE_STATE

from ..adapters.ingestion_workflow_stores import (
    SqlAlchemyIngestionJobStore,
    SqlAlchemyReplayAuditStore,
)
from ..DTOs.ingestion_job_dto import (
    ConsumerDlqEventResponse,
    IngestionBacklogBreakdownResponse,
    IngestionCapacityStatusResponse,
    IngestionConsumerLagResponse,
    IngestionErrorBudgetStatusResponse,
    IngestionHealthSummaryResponse,
    IngestionIdempotencyDiagnosticsResponse,
    IngestionJobFailureResponse,
    IngestionJobRecordStatusResponse,
    IngestionJobResponse,
    IngestionJobStatus,
    IngestionOperatingBandResponse,
    IngestionOpsModeResponse,
    IngestionOpsPolicyResponse,
    IngestionReplayAuditResponse,
    IngestionReprocessingQueueHealthResponse,
    IngestionSloStatusResponse,
    IngestionStalledJobListResponse,
)
from ..ports.ingestion_workflow_stores import (
    IngestionJobStore,
    ReplayAuditRecord,
    ReplayAuditStore,
)
from ..settings import get_ingestion_service_settings
from . import ingestion_capacity_status as _capacity_status
from . import ingestion_error_budget_status as _error_budget_status
from .ingestion_backlog_breakdown import load_backlog_breakdown_response
from .ingestion_consumer_dlq_events import (
    get_consumer_dlq_event_response,
    list_consumer_dlq_event_responses,
)
from .ingestion_consumer_lag import load_consumer_lag_response
from .ingestion_health_summary import load_health_summary_response
from .ingestion_idempotency_diagnostics import load_idempotency_diagnostics_response
from .ingestion_job_lifecycle import (
    IngestionJobCreateResult,
    IngestionJobReplayContext,
    get_job_replay_context_response,
    get_job_response,
    list_failure_responses,
    mark_job_failed,
    mark_job_queued,
    mark_job_retried,
    mark_job_retried_and_queued,
    record_job_failure_observation,
)
from .ingestion_job_listing import (
    IngestionJobListFilters,
    load_job_list_response,
    load_latest_replayable_job_by_correlation_id,
)
from .ingestion_operating_band import (
    build_operating_band_policy,
    load_operating_band_response,
)
from .ingestion_operating_policy import (
    build_operating_policy_config,
    build_operating_policy_response,
)
from .ingestion_ops_mode import (
    assert_ingestion_writable_mode,
    load_ops_mode_response,
    update_ops_mode_response,
)
from .ingestion_record_status import load_record_status_response
from .ingestion_reprocessing_queue_health import load_reprocessing_queue_health_response
from .ingestion_retry_permissions import (
    assert_reprocessing_publish_allowed_for_count,
    assert_retry_allowed_for_record_count,
    count_backlog_jobs,
)
from .ingestion_slo_status import (
    load_slo_status_response,
)
from .ingestion_stalled_jobs import load_stalled_job_list_response

_SETTINGS = get_ingestion_service_settings()
_RUNTIME_POLICY = _SETTINGS.runtime_policy

REPLAY_MAX_RECORDS_PER_REQUEST = _RUNTIME_POLICY.replay_max_records_per_request
REPLAY_MAX_BACKLOG_JOBS = _RUNTIME_POLICY.replay_max_backlog_jobs
DLQ_BUDGET_EVENTS_PER_WINDOW = _RUNTIME_POLICY.dlq_budget_events_per_window
CAPACITY_ASSUMED_REPLICAS = _RUNTIME_POLICY.capacity_assumed_replicas
logger = logging.getLogger(__name__)


OPERATING_BAND_POLICY = build_operating_band_policy(_RUNTIME_POLICY.operating_band)


_derive_capacity_group = _capacity_status._derive_capacity_group


class IngestionJobService:
    """
    Persists ingestion lifecycle and operational controls for ingestion runbooks.
    """

    def __init__(
        self,
        *,
        session_factory=None,
        job_store: IngestionJobStore | None = None,
        replay_audit_store: ReplayAuditStore | None = None,
    ) -> None:
        self._session_factory_override = session_factory
        self._job_store = job_store
        self._replay_audit_store = replay_audit_store

    def _session_factory(self):
        return self._session_factory_override or get_async_db_session

    def _default_job_store(self) -> IngestionJobStore:
        return SqlAlchemyIngestionJobStore(session_factory=self._session_factory())

    def _default_replay_audit_store(self) -> ReplayAuditStore:
        return SqlAlchemyReplayAuditStore(session_factory=self._session_factory())

    @property
    def _job_store_adapter(self) -> IngestionJobStore:
        return self._job_store or self._default_job_store()

    @property
    def _replay_audit_store_adapter(self) -> ReplayAuditStore:
        return self._replay_audit_store or self._default_replay_audit_store()

    async def create_or_get_job(
        self,
        *,
        job_id: str,
        endpoint: str,
        entity_type: str,
        accepted_count: int,
        idempotency_key: str | None,
        correlation_id: str,
        request_id: str,
        trace_id: str,
        request_payload: dict[str, Any] | None,
    ) -> IngestionJobCreateResult:
        return await self._job_store_adapter.create_or_get_job(
            job_id=job_id,
            endpoint=endpoint,
            entity_type=entity_type,
            accepted_count=accepted_count,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            request_id=request_id,
            trace_id=trace_id,
            request_payload=request_payload,
        )

    async def mark_queued(self, job_id: str, *, expected_statuses=None) -> bool:
        return await mark_job_queued(
            job_id=job_id,
            expected_statuses=expected_statuses,
            session_factory=get_async_db_session,
        )

    async def mark_failed(
        self,
        job_id: str,
        failure_reason: str,
        failure_phase: str = "publish",
        failed_record_keys: list[str] | None = None,
    ) -> bool:
        return await mark_job_failed(
            job_id=job_id,
            failure_reason=failure_reason,
            failure_phase=failure_phase,
            failed_record_keys=failed_record_keys,
            session_factory=get_async_db_session,
        )

    async def record_failure_observation(
        self,
        job_id: str,
        failure_reason: str,
        *,
        failure_phase: str,
        failed_record_keys: list[str] | None = None,
    ) -> None:
        await record_job_failure_observation(
            job_id=job_id,
            failure_reason=failure_reason,
            failure_phase=failure_phase,
            failed_record_keys=failed_record_keys,
            session_factory=get_async_db_session,
        )

    async def mark_retried(self, job_id: str) -> bool:
        return await mark_job_retried(job_id=job_id, session_factory=get_async_db_session)

    async def mark_retried_and_queued(self, job_id: str) -> bool:
        return await mark_job_retried_and_queued(
            job_id=job_id,
            session_factory=get_async_db_session,
        )

    async def get_job(self, job_id: str) -> IngestionJobResponse | None:
        return await get_job_response(job_id=job_id, session_factory=get_async_db_session)

    async def get_job_replay_context(self, job_id: str) -> IngestionJobReplayContext | None:
        return await get_job_replay_context_response(
            job_id=job_id,
            session_factory=get_async_db_session,
        )

    async def get_latest_replayable_job_by_correlation_id(
        self,
        correlation_id: str,
    ) -> IngestionJobResponse | None:
        return await load_latest_replayable_job_by_correlation_id(
            correlation_id=correlation_id,
            session_factory=get_async_db_session,
        )

    async def list_jobs(
        self,
        *,
        status: IngestionJobStatus | None = None,
        entity_type: str | None = None,
        submitted_from: datetime | None = None,
        submitted_to: datetime | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> tuple[list[IngestionJobResponse], str | None]:
        return await load_job_list_response(
            filters=IngestionJobListFilters(
                status=status,
                entity_type=entity_type,
                submitted_from=submitted_from,
                submitted_to=submitted_to,
            ),
            cursor=cursor,
            limit=limit,
            session_factory=get_async_db_session,
        )

    async def list_failures(
        self, job_id: str, limit: int = 100
    ) -> list[IngestionJobFailureResponse]:
        return await list_failure_responses(
            job_id=job_id,
            limit=limit,
            session_factory=get_async_db_session,
        )

    async def get_health_summary(self) -> IngestionHealthSummaryResponse:
        return await load_health_summary_response(
            session_factory=get_async_db_session,
        )

    async def get_slo_status(
        self,
        *,
        lookback_minutes: int = 60,
        failure_rate_threshold: Decimal = Decimal("0.03"),
        queue_latency_threshold_seconds: float = 5.0,
        backlog_age_threshold_seconds: float = 300.0,
    ) -> IngestionSloStatusResponse:
        return await load_slo_status_response(
            lookback_minutes=lookback_minutes,
            failure_rate_threshold=failure_rate_threshold,
            queue_latency_threshold_seconds=queue_latency_threshold_seconds,
            backlog_age_threshold_seconds=backlog_age_threshold_seconds,
            session_factory=get_async_db_session,
            backlog_age_metric=INGESTION_BACKLOG_AGE_SECONDS,
            logger=logger,
        )

    async def get_operating_band(
        self,
        *,
        lookback_minutes: int = 60,
        failure_rate_threshold: Decimal = Decimal("0.03"),
        queue_latency_threshold_seconds: float = 5.0,
        backlog_age_threshold_seconds: float = 300.0,
    ) -> IngestionOperatingBandResponse:
        return await load_operating_band_response(
            lookback_minutes=lookback_minutes,
            failure_rate_threshold=failure_rate_threshold,
            queue_latency_threshold_seconds=queue_latency_threshold_seconds,
            backlog_age_threshold_seconds=backlog_age_threshold_seconds,
            policy=OPERATING_BAND_POLICY,
            slo_status_loader=self.get_slo_status,
            error_budget_status_loader=self.get_error_budget_status,
        )

    async def get_operating_policy(self) -> IngestionOpsPolicyResponse:
        return build_operating_policy_response(
            build_operating_policy_config(
                runtime_policy=_RUNTIME_POLICY,
                operating_band_policy=OPERATING_BAND_POLICY,
            ),
        )

    async def get_reprocessing_queue_health(self) -> IngestionReprocessingQueueHealthResponse:
        return await load_reprocessing_queue_health_response(
            session_factory=get_async_db_session,
        )

    async def get_capacity_status(
        self,
        *,
        lookback_minutes: int = 60,
        limit: int = 200,
        assumed_replicas: int | None = None,
    ) -> IngestionCapacityStatusResponse:
        return await _capacity_status.load_capacity_status_response(
            lookback_minutes=lookback_minutes,
            limit=limit,
            assumed_replicas=assumed_replicas,
            default_assumed_replicas=CAPACITY_ASSUMED_REPLICAS,
            session_factory=get_async_db_session,
        )

    async def get_backlog_breakdown(
        self,
        *,
        lookback_minutes: int = 1440,
        limit: int = 200,
    ) -> IngestionBacklogBreakdownResponse:
        return await load_backlog_breakdown_response(
            lookback_minutes=lookback_minutes,
            limit=limit,
            session_factory=get_async_db_session,
        )

    async def list_stalled_jobs(
        self,
        *,
        threshold_seconds: int = 300,
        limit: int = 100,
    ) -> IngestionStalledJobListResponse:
        return await load_stalled_job_list_response(
            threshold_seconds=threshold_seconds,
            limit=limit,
            session_factory=get_async_db_session,
        )

    async def list_consumer_dlq_events(
        self,
        *,
        limit: int = 100,
        original_topic: str | None = None,
        consumer_group: str | None = None,
    ) -> list[ConsumerDlqEventResponse]:
        return await list_consumer_dlq_event_responses(
            limit=limit,
            original_topic=original_topic,
            consumer_group=consumer_group,
            session_factory=get_async_db_session,
        )

    async def get_consumer_dlq_event(self, event_id: str) -> ConsumerDlqEventResponse | None:
        return await get_consumer_dlq_event_response(
            event_id=event_id,
            session_factory=get_async_db_session,
        )

    async def find_successful_replay_audit_by_fingerprint(
        self,
        replay_fingerprint: str,
        recovery_path: str | None = None,
    ) -> dict[str, str] | None:
        return await self._replay_audit_store_adapter.find_successful_replay_audit_by_fingerprint(
            replay_fingerprint=replay_fingerprint,
            recovery_path=recovery_path,
        )

    async def record_consumer_dlq_replay_audit(
        self,
        *,
        recovery_path: str,
        event_id: str,
        replay_fingerprint: str,
        correlation_id: str | None,
        job_id: str | None,
        endpoint: str | None,
        replay_status: str,
        dry_run: bool,
        replay_reason: str,
        requested_by: str | None,
        correlation_missing_reason: str | None = None,
        alternate_lookup_key: str | None = None,
    ) -> str:
        return await self._replay_audit_store_adapter.record_consumer_dlq_replay_audit(
            ReplayAuditRecord(
                recovery_path=recovery_path,
                event_id=event_id,
                replay_fingerprint=replay_fingerprint,
                correlation_id=correlation_id,
                correlation_missing_reason=correlation_missing_reason,
                alternate_lookup_key=alternate_lookup_key,
                job_id=job_id,
                endpoint=endpoint,
                replay_status=replay_status,
                dry_run=dry_run,
                replay_reason=replay_reason,
                requested_by=requested_by,
            )
        )

    async def get_replay_audit(self, replay_id: str) -> IngestionReplayAuditResponse | None:
        return await self._replay_audit_store_adapter.get_replay_audit(
            replay_id=replay_id,
        )

    async def list_replay_audits(
        self,
        *,
        limit: int = 100,
        recovery_path: str | None = None,
        replay_status: str | None = None,
        replay_fingerprint: str | None = None,
        job_id: str | None = None,
    ) -> list[IngestionReplayAuditResponse]:
        return await self._replay_audit_store_adapter.list_replay_audits(
            limit=limit,
            recovery_path=recovery_path,
            replay_status=replay_status,
            replay_fingerprint=replay_fingerprint,
            job_id=job_id,
        )

    async def get_consumer_lag(
        self,
        *,
        lookback_minutes: int = 60,
        limit: int = 100,
    ) -> IngestionConsumerLagResponse:
        return await load_consumer_lag_response(
            lookback_minutes=lookback_minutes,
            limit=limit,
            session_factory=get_async_db_session,
            health_summary_loader=self.get_health_summary,
        )

    async def get_job_record_status(self, job_id: str) -> IngestionJobRecordStatusResponse | None:
        return await load_record_status_response(
            job_id=job_id,
            session_factory=get_async_db_session,
        )

    async def get_idempotency_diagnostics(
        self,
        *,
        lookback_minutes: int = 1440,
        limit: int = 200,
    ) -> IngestionIdempotencyDiagnosticsResponse:
        return await load_idempotency_diagnostics_response(
            lookback_minutes=lookback_minutes,
            limit=limit,
            session_factory=get_async_db_session,
        )

    async def get_error_budget_status(
        self,
        *,
        lookback_minutes: int = 60,
        failure_rate_threshold: Decimal = Decimal("0.03"),
        backlog_growth_threshold: int = 5,
    ) -> IngestionErrorBudgetStatusResponse:
        return await _error_budget_status.load_error_budget_status_response(
            lookback_minutes=lookback_minutes,
            failure_rate_threshold=failure_rate_threshold,
            backlog_growth_threshold=backlog_growth_threshold,
            replay_max_backlog_jobs=REPLAY_MAX_BACKLOG_JOBS,
            dlq_budget_events_per_window=DLQ_BUDGET_EVENTS_PER_WINDOW,
            session_factory=get_async_db_session,
            logger=logger,
        )

    async def get_ops_mode(self) -> IngestionOpsModeResponse:
        return await load_ops_mode_response(session_factory=get_async_db_session)

    async def update_ops_mode(
        self,
        *,
        mode: str,
        replay_window_start: datetime | None,
        replay_window_end: datetime | None,
        updated_by: str | None,
    ) -> IngestionOpsModeResponse:
        return await update_ops_mode_response(
            mode=mode,
            replay_window_start=replay_window_start,
            replay_window_end=replay_window_end,
            updated_by=updated_by,
            session_factory=get_async_db_session,
        )

    async def assert_ingestion_writable(self) -> None:
        await assert_ingestion_writable_mode(
            ops_mode_loader=self.get_ops_mode,
            mode_state_metric=INGESTION_MODE_STATE,
        )

    async def assert_retry_allowed(self, submitted_at: datetime) -> None:
        await self.assert_retry_allowed_for_records(
            submitted_at=submitted_at,
            replay_record_count=1,
        )

    async def _count_backlog_jobs(self) -> int:
        return await count_backlog_jobs(session_factory=get_async_db_session)

    async def assert_retry_allowed_for_records(
        self,
        *,
        submitted_at: datetime,
        replay_record_count: int,
    ) -> None:
        await assert_retry_allowed_for_record_count(
            submitted_at=submitted_at,
            replay_record_count=replay_record_count,
            ops_mode_loader=self.get_ops_mode,
            backlog_counter=self._count_backlog_jobs,
            max_records_per_request=REPLAY_MAX_RECORDS_PER_REQUEST,
            max_backlog_jobs=REPLAY_MAX_BACKLOG_JOBS,
        )

    async def assert_reprocessing_publish_allowed(self, record_count: int) -> None:
        await assert_reprocessing_publish_allowed_for_count(
            record_count=record_count,
            retry_permission_checker=self.assert_retry_allowed_for_records,
        )


_INGESTION_JOB_SERVICE = IngestionJobService()


def get_ingestion_job_service() -> IngestionJobService:
    return _INGESTION_JOB_SERVICE
