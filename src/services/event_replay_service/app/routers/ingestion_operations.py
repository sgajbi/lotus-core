from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, status

from src.services.ingestion_service.app.DTOs.ingestion_job_dto import (
    ConsumerDlqEventListResponse,
    ConsumerDlqReplayRequest,
    ConsumerDlqReplayResponse,
    IngestionBacklogBreakdownResponse,
    IngestionCapacityStatusResponse,
    IngestionConsumerLagResponse,
    IngestionErrorBudgetStatusResponse,
    IngestionHealthSummaryResponse,
    IngestionIdempotencyDiagnosticsResponse,
    IngestionJobBookkeepingRepairResponse,
    IngestionJobFailureListResponse,
    IngestionJobListResponse,
    IngestionJobRecordStatusResponse,
    IngestionJobResponse,
    IngestionJobStatus,
    IngestionOperatingBandResponse,
    IngestionOpsModeResponse,
    IngestionOpsModeUpdateRequest,
    IngestionOpsPolicyResponse,
    IngestionReplayAuditListResponse,
    IngestionReplayAuditResponse,
    IngestionReprocessingQueueHealthResponse,
    IngestionRetryRequest,
    IngestionSloStatusResponse,
    IngestionStalledJobListResponse,
)
from src.services.ingestion_service.app.ops_controls import require_ops_token
from src.services.ingestion_service.app.services.ingestion_job_service import (
    IngestionJobService,
    get_ingestion_job_service,
)

from ..application.bookkeeping_repair_commands import (
    BookkeepingRepairCommandError,
    BookkeepingRepairCommandService,
)
from ..application.consumer_dlq_replay_commands import (
    ConsumerDlqReplayCommand,
    ConsumerDlqReplayCommandService,
)
from ..application.ingestion_operations_queries import (
    IngestionOperationsNotFound,
    IngestionOperationsQueryService,
)
from ..application.ingestion_retry_commands import (
    IngestionRetryCommandService,
)
from ..application.ops_control_commands import (
    OpsControlCommandError,
    OpsControlCommandService,
    OpsControlUpdateCommand,
)
from ..application.replay_command_errors import ReplayCommandError
from ..dependencies import (
    get_bookkeeping_repair_command_service,
    get_consumer_dlq_replay_command_service,
    get_ingestion_operations_query_service,
    get_ingestion_retry_command_service,
    get_ops_control_command_service,
)
from .ingestion_operations_examples import (
    CONSUMER_DLQ_EVENT_LIST_RESPONSE_EXAMPLE,
    CONSUMER_DLQ_REPLAY_REQUEST_EXAMPLES,
    CONSUMER_DLQ_REPLAY_RESPONSE_EXAMPLE,
    INGESTION_BACKLOG_BREAKDOWN_RESPONSE_EXAMPLE,
    INGESTION_BOOKKEEPING_REPAIR_FAILED_EXAMPLE,
    INGESTION_BOOKKEEPING_REPAIR_NOT_ELIGIBLE_EXAMPLE,
    INGESTION_BOOKKEEPING_REPAIR_RESPONSE_EXAMPLE,
    INGESTION_CAPACITY_STATUS_RESPONSE_EXAMPLE,
    INGESTION_CONSUMER_DLQ_EVENT_NOT_FOUND_EXAMPLE,
    INGESTION_CONSUMER_LAG_RESPONSE_EXAMPLE,
    INGESTION_ERROR_BUDGET_STATUS_RESPONSE_EXAMPLE,
    INGESTION_HEALTH_SUMMARY_RESPONSE_EXAMPLE,
    INGESTION_IDEMPOTENCY_DIAGNOSTICS_RESPONSE_EXAMPLE,
    INGESTION_JOB_FAILURE_LIST_RESPONSE_EXAMPLE,
    INGESTION_JOB_NOT_FOUND_EXAMPLE,
    INGESTION_JOB_PARTIAL_RETRY_UNSUPPORTED_EXAMPLE,
    INGESTION_JOB_RECORD_STATUS_RESPONSE_EXAMPLE,
    INGESTION_JOB_RESPONSE_EXAMPLE,
    INGESTION_JOB_RETRY_BLOCKED_EXAMPLE,
    INGESTION_JOB_RETRY_BOOKKEEPING_FAILED_EXAMPLE,
    INGESTION_JOB_RETRY_DUPLICATE_BLOCKED_EXAMPLE,
    INGESTION_JOB_RETRY_PUBLISH_FAILED_EXAMPLE,
    INGESTION_JOB_RETRY_UNSUPPORTED_EXAMPLE,
    INGESTION_OPERATING_BAND_RESPONSE_EXAMPLE,
    INGESTION_OPS_MODE_EXAMPLE,
    INGESTION_OPS_POLICY_RESPONSE_EXAMPLE,
    INGESTION_REPLAY_AUDIT_LIST_RESPONSE_EXAMPLE,
    INGESTION_REPLAY_AUDIT_NOT_FOUND_EXAMPLE,
    INGESTION_REPLAY_AUDIT_RESPONSE_EXAMPLE,
    INGESTION_REPLAY_AUDIT_WRITE_FAILED_EXAMPLE,
    INGESTION_REPROCESSING_QUEUE_HEALTH_RESPONSE_EXAMPLE,
    INGESTION_RETRY_REQUEST_EXAMPLES,
    INGESTION_SLO_STATUS_RESPONSE_EXAMPLE,
    INGESTION_STALLED_JOB_LIST_RESPONSE_EXAMPLE,
)

router = APIRouter(dependencies=[Depends(require_ops_token)])


def _not_found_response(exc: IngestionOperationsNotFound) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": exc.code, "message": exc.message},
    )


@router.get(
    "/ingestion/jobs/{job_id}",
    response_model=IngestionJobResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="Get ingestion job status",
    description=(
        "What: Return lifecycle state and metadata for one ingestion job.\n"
        "How: Read canonical ingestion-job state by job_id.\n"
        "When: Use to track asynchronous ingestion completion or failure for a submitted request."
    ),
    responses={
        200: {
            "description": "One ingestion job.",
            "content": {"application/json": {"example": INGESTION_JOB_RESPONSE_EXAMPLE}},
        },
        404: {
            "description": "Ingestion job was not found.",
            "content": {"application/json": {"example": INGESTION_JOB_NOT_FOUND_EXAMPLE}},
        },
    },
)
async def get_ingestion_job(
    job_id: str = Path(
        description="Ingestion job identifier.",
        examples=["job_01J5S0J6D3BAVMK2E1V0WQ7MCC"],
    ),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    job = await ingestion_job_service.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "INGESTION_JOB_NOT_FOUND",
                "message": f"Ingestion job '{job_id}' was not found.",
            },
        )
    return job


@router.post(
    "/ingestion/jobs/{job_id}/bookkeeping/repair",
    response_model=IngestionJobBookkeepingRepairResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="Repair post-publish ingestion job bookkeeping",
    description=(
        "What: Repair a job left accepted after publish or persist work completed but "
        "bookkeeping failed.\n"
        "How: Require recorded `queue_bookkeeping` or `persist_bookkeeping` failure evidence "
        "before marking the job queued.\n"
        "When: Use after a client receives `INGESTION_JOB_BOOKKEEPING_FAILED` and operators "
        "confirm the work completed."
    ),
    responses={
        200: {
            "description": "Bookkeeping repair was applied or was already reflected.",
            "content": {
                "application/json": {"example": INGESTION_BOOKKEEPING_REPAIR_RESPONSE_EXAMPLE}
            },
        },
        404: {
            "description": "Ingestion job was not found.",
            "content": {"application/json": {"example": INGESTION_JOB_NOT_FOUND_EXAMPLE}},
        },
        409: {
            "description": "Ingestion job does not have post-publish bookkeeping failure evidence.",
            "content": {
                "application/json": {"example": INGESTION_BOOKKEEPING_REPAIR_NOT_ELIGIBLE_EXAMPLE}
            },
        },
        500: {
            "description": "Bookkeeping repair did not complete.",
            "content": {
                "application/json": {"example": INGESTION_BOOKKEEPING_REPAIR_FAILED_EXAMPLE}
            },
        },
    },
)
async def repair_ingestion_job_bookkeeping(
    job_id: str = Path(
        description="Ingestion job identifier.",
        examples=["job_01J5S0J6D3BAVMK2E1V0WQ7MCC"],
    ),
    command_service: BookkeepingRepairCommandService = Depends(
        get_bookkeeping_repair_command_service
    ),
):
    try:
        result = await command_service.repair_ingestion_job_bookkeeping(job_id=job_id)
    except BookkeepingRepairCommandError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return IngestionJobBookkeepingRepairResponse(**result.to_response_payload())


@router.get(
    "/ingestion/jobs",
    response_model=IngestionJobListResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="List ingestion jobs",
    description=(
        "What: List ingestion jobs with operational filtering and pagination.\n"
        "How: Query canonical job records using status/entity/date filters and cursor pagination.\n"
        "When: Use for runbook dashboards, triage, and service-operations monitoring."
    ),
    responses={
        200: {
            "description": "Filtered ingestion jobs.",
            "content": {
                "application/json": {
                    "example": {
                        "jobs": [INGESTION_JOB_RESPONSE_EXAMPLE],
                        "total": 1,
                        "next_cursor": "job_01J5S0J6D3BAVMK2E1V0WQ7MCC",
                    }
                }
            },
        }
    },
)
async def list_ingestion_jobs(
    status: IngestionJobStatus | None = Query(
        default=None,
        description="Optional job status filter.",
        examples=["queued"],
    ),
    entity_type: str | None = Query(
        default=None,
        description="Optional canonical entity type filter.",
        examples=["transaction"],
    ),
    submitted_from: datetime | None = Query(
        default=None,
        description="Optional inclusive lower bound for job submission timestamp.",
        examples=["2026-03-06T00:00:00Z"],
    ),
    submitted_to: datetime | None = Query(
        default=None,
        description="Optional inclusive upper bound for job submission timestamp.",
        examples=["2026-03-06T23:59:59Z"],
    ),
    cursor: str | None = Query(
        default=None,
        description="Opaque pagination cursor from the previous page.",
        examples=["job_01J5S0J6D3BAVMK2E1V0WQ7MCC"],
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
        description="Maximum number of jobs to return.",
        examples=[100],
    ),
    query_service: IngestionOperationsQueryService = Depends(
        get_ingestion_operations_query_service
    ),
):
    page = await query_service.list_jobs(
        status=status,
        entity_type=entity_type,
        submitted_from=submitted_from,
        submitted_to=submitted_to,
        cursor=cursor,
        limit=limit,
    )
    return IngestionJobListResponse(
        jobs=page.jobs,
        total=page.total,
        next_cursor=page.next_cursor,
    )


@router.get(
    "/ingestion/jobs/{job_id}/failures",
    response_model=IngestionJobFailureListResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="List ingestion job failures",
    description=(
        "What: Return failure events recorded for a specific ingestion job.\n"
        "How: Read ingestion job failure history with most-recent-first ordering.\n"
        "When: Use during incident triage to identify failure phases and impacted record keys."
    ),
    responses={
        200: {
            "description": "Failure events for the requested ingestion job.",
            "content": {
                "application/json": {"example": INGESTION_JOB_FAILURE_LIST_RESPONSE_EXAMPLE}
            },
        },
        404: {
            "description": "Ingestion job not found.",
            "content": {"application/json": {"example": INGESTION_JOB_NOT_FOUND_EXAMPLE}},
        },
    },
)
async def list_ingestion_job_failures(
    job_id: str = Path(
        description="Ingestion job identifier.",
        examples=["job_01J5S0J6D3BAVMK2E1V0WQ7MCC"],
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
        description="Maximum number of failure events to return.",
        examples=[100],
    ),
    query_service: IngestionOperationsQueryService = Depends(
        get_ingestion_operations_query_service
    ),
):
    try:
        page = await query_service.list_job_failures(job_id=job_id, limit=limit)
    except IngestionOperationsNotFound as exc:
        raise _not_found_response(exc) from exc
    return IngestionJobFailureListResponse(failures=page.failures, total=page.total)


@router.get(
    "/ingestion/jobs/{job_id}/records",
    response_model=IngestionJobRecordStatusResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="Get ingestion job record-level status",
    description=(
        "What: Return record-level replayability and failed keys for an ingestion job.\n"
        "How: Derive replayable keys from stored payload and merge with failure history.\n"
        "When: Use before partial retry operations or to build precise remediation batches."
    ),
    responses={
        200: {
            "description": "Record-level replayability and failed keys for the ingestion job.",
            "content": {
                "application/json": {"example": INGESTION_JOB_RECORD_STATUS_RESPONSE_EXAMPLE}
            },
        },
        404: {
            "description": "Ingestion job not found.",
            "content": {"application/json": {"example": INGESTION_JOB_NOT_FOUND_EXAMPLE}},
        },
    },
)
async def get_ingestion_job_records(
    job_id: str = Path(
        description="Ingestion job identifier.",
        examples=["job_01J5S0J6D3BAVMK2E1V0WQ7MCC"],
    ),
    query_service: IngestionOperationsQueryService = Depends(
        get_ingestion_operations_query_service
    ),
):
    try:
        return await query_service.get_job_record_status(job_id)
    except IngestionOperationsNotFound as exc:
        raise _not_found_response(exc) from exc


@router.post(
    "/ingestion/jobs/{job_id}/retry",
    response_model=IngestionJobResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="Retry a failed ingestion job",
    description=(
        "What: Retry a failed ingestion job using full or partial payload replay.\n"
        "How: Rehydrate stored request payload, apply optional record-key filtering, "
        "and republish asynchronously.\n"
        "When: Use after root cause remediation to recover failed ingestion "
        "without direct DB operations."
    ),
    responses={
        200: {
            "description": "Ingestion job accepted for replay or replay dry-run completed.",
            "content": {"application/json": {"example": INGESTION_JOB_RESPONSE_EXAMPLE}},
        },
        404: {
            "description": "Ingestion job was not found.",
            "content": {"application/json": {"example": INGESTION_JOB_NOT_FOUND_EXAMPLE}},
        },
        409: {
            "description": "Retry is not allowed or replay is unsupported for the requested scope.",
            "content": {
                "application/json": {
                    "examples": {
                        "retry_unsupported": {"value": INGESTION_JOB_RETRY_UNSUPPORTED_EXAMPLE},
                        "partial_retry_unsupported": {
                            "value": INGESTION_JOB_PARTIAL_RETRY_UNSUPPORTED_EXAMPLE
                        },
                        "retry_blocked": {"value": INGESTION_JOB_RETRY_BLOCKED_EXAMPLE},
                        "duplicate_blocked": {
                            "value": INGESTION_JOB_RETRY_DUPLICATE_BLOCKED_EXAMPLE
                        },
                    }
                }
            },
        },
        500: {
            "description": "Replay audit or retry bookkeeping failed.",
            "content": {
                "application/json": {
                    "examples": {
                        "retry_publish_failed": {
                            "value": INGESTION_JOB_RETRY_PUBLISH_FAILED_EXAMPLE
                        },
                        "retry_bookkeeping_failed": {
                            "value": INGESTION_JOB_RETRY_BOOKKEEPING_FAILED_EXAMPLE
                        },
                        "replay_audit_write_failed": {
                            "value": INGESTION_REPLAY_AUDIT_WRITE_FAILED_EXAMPLE
                        },
                    }
                }
            },
        },
    },
)
async def retry_ingestion_job(
    job_id: str = Path(
        description="Ingestion job identifier.",
        examples=["job_01J5S0J6D3BAVMK2E1V0WQ7MCC"],
    ),
    retry_request: IngestionRetryRequest = Body(
        default_factory=IngestionRetryRequest,
        openapi_examples=INGESTION_RETRY_REQUEST_EXAMPLES,
    ),
    ops_actor: str = Depends(require_ops_token),
    command_service: IngestionRetryCommandService = Depends(get_ingestion_retry_command_service),
):
    try:
        return await command_service.retry_ingestion_job(
            job_id=job_id,
            retry_request=retry_request,
            requested_by=ops_actor,
        )
    except ReplayCommandError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get(
    "/ingestion/health/summary",
    response_model=IngestionHealthSummaryResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="Get ingestion operational health summary",
    description=(
        "What: Return aggregate ingestion counters (accepted/queued/failed/backlog).\n"
        "How: Compute summary from canonical ingestion job state.\n"
        "When: Use for fast operational health checks and dashboards."
    ),
    responses={
        status.HTTP_200_OK: {
            "description": "Current aggregate ingestion job health counters.",
            "content": {"application/json": {"example": INGESTION_HEALTH_SUMMARY_RESPONSE_EXAMPLE}},
        }
    },
)
async def get_ingestion_health_summary(
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    return await ingestion_job_service.get_health_summary()


@router.get(
    "/ingestion/health/lag",
    response_model=IngestionHealthSummaryResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="Get ingestion backlog indicators",
    description=(
        "What: Return backlog-oriented counters derived from non-terminal jobs.\n"
        "How: Reuse canonical health summary state for lag visibility.\n"
        "When: Use when operations need a quick backlog signal during ingestion incidents."
    ),
    responses={
        status.HTTP_200_OK: {
            "description": "Current backlog-oriented ingestion health counters.",
            "content": {"application/json": {"example": INGESTION_HEALTH_SUMMARY_RESPONSE_EXAMPLE}},
        }
    },
)
async def get_ingestion_health_lag(
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    return await ingestion_job_service.get_health_summary()


@router.get(
    "/ingestion/health/consumer-lag",
    response_model=IngestionConsumerLagResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="Get consumer lag diagnostics",
    description=(
        "What: Return consumer lag diagnostics derived from DLQ pressure and backlog signals.\n"
        "How: Aggregate consumer dead-letter events by consumer group and original topic.\n"
        "When: Use to triage downstream consumer lag before replaying ingestion jobs."
    ),
    responses={
        status.HTTP_200_OK: {
            "description": "Consumer-group/topic lag diagnostics for the requested lookback.",
            "content": {"application/json": {"example": INGESTION_CONSUMER_LAG_RESPONSE_EXAMPLE}},
        }
    },
)
async def get_ingestion_consumer_lag(
    lookback_minutes: int = Query(
        default=60,
        ge=5,
        le=1440,
        description="Lookback window, in minutes, used to aggregate consumer lag diagnostics.",
        examples=[60],
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
        description="Maximum number of consumer-group/topic lag rows to return.",
        examples=[100],
    ),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    return await ingestion_job_service.get_consumer_lag(
        lookback_minutes=lookback_minutes,
        limit=limit,
    )


@router.get(
    "/ingestion/health/slo",
    response_model=IngestionSloStatusResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="Evaluate ingestion SLO status",
    description=(
        "What: Evaluate ingestion SLO signals for failure rate, queue latency, and backlog age.\n"
        "How: Compute lookback-window metrics and compare against caller thresholds.\n"
        "When: Use for alert evaluation, on-call triage, and operational readiness checks."
    ),
    responses={
        status.HTTP_200_OK: {
            "description": "Current ingestion SLO status for the requested thresholds.",
            "content": {"application/json": {"example": INGESTION_SLO_STATUS_RESPONSE_EXAMPLE}},
        }
    },
)
async def get_ingestion_slo_status(
    lookback_minutes: int = Query(
        default=60,
        ge=5,
        le=1440,
        description="Lookback window, in minutes, used to compute ingestion SLO metrics.",
        examples=[60],
    ),
    failure_rate_threshold: Decimal = Query(
        default=Decimal("0.03"),
        ge=0,
        le=1,
        description="Failure-rate threshold used to flag SLO breaches.",
        examples=["0.03"],
    ),
    queue_latency_threshold_seconds: float = Query(
        default=5.0,
        ge=0.1,
        le=600,
        description="Queue-latency threshold, in seconds, used for SLO evaluation.",
        examples=[5.0],
    ),
    backlog_age_threshold_seconds: float = Query(
        default=300,
        ge=1,
        le=86400,
        description="Oldest-backlog-age threshold, in seconds, used for SLO evaluation.",
        examples=[300.0],
    ),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    return await ingestion_job_service.get_slo_status(
        lookback_minutes=lookback_minutes,
        failure_rate_threshold=failure_rate_threshold,
        queue_latency_threshold_seconds=queue_latency_threshold_seconds,
        backlog_age_threshold_seconds=backlog_age_threshold_seconds,
    )


@router.get(
    "/ingestion/health/error-budget",
    response_model=IngestionErrorBudgetStatusResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="Get ingestion error-budget and backlog-growth status",
    description=(
        "What: Return current error-budget consumption and backlog growth trend.\n"
        "How: Compare failure/backlog metrics across current and previous lookback windows.\n"
        "When: Use for SRE-style burn-rate alerts and release-go/no-go operational checks."
    ),
    responses={
        status.HTTP_200_OK: {
            "description": "Current ingestion error-budget and backlog-growth status.",
            "content": {
                "application/json": {"example": INGESTION_ERROR_BUDGET_STATUS_RESPONSE_EXAMPLE}
            },
        }
    },
)
async def get_ingestion_error_budget_status(
    lookback_minutes: int = Query(
        default=60,
        ge=5,
        le=1440,
        description=(
            "Lookback window, in minutes, used for current-vs-previous error-budget comparison."
        ),
        examples=[60],
    ),
    failure_rate_threshold: Decimal = Query(
        default=Decimal("0.03"),
        ge=0,
        le=1,
        description="Failure-rate threshold used when computing burn-rate breach state.",
        examples=["0.03"],
    ),
    backlog_growth_threshold: int = Query(
        default=5,
        ge=0,
        le=10000,
        description="Backlog-growth threshold, in jobs, used for error-budget alerting.",
        examples=[5],
    ),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    return await ingestion_job_service.get_error_budget_status(
        lookback_minutes=lookback_minutes,
        failure_rate_threshold=failure_rate_threshold,
        backlog_growth_threshold=backlog_growth_threshold,
    )


@router.get(
    "/ingestion/health/operating-band",
    response_model=IngestionOperatingBandResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="Get ingestion operating band",
    description=(
        "What: Return canonical ingestion operating band (green/yellow/orange/red).\n"
        "How: Combine backlog-age, DLQ pressure, and SLO breach signals into one "
        "runbook-ready severity.\n"
        "When: Use for autoscaling decisions, replay safety gating, and incident "
        "triage automation."
    ),
    responses={
        status.HTTP_200_OK: {
            "description": "Canonical ingestion operating severity band and runbook action.",
            "content": {"application/json": {"example": INGESTION_OPERATING_BAND_RESPONSE_EXAMPLE}},
        }
    },
)
async def get_ingestion_operating_band(
    lookback_minutes: int = Query(
        default=60,
        ge=5,
        le=1440,
        description="Lookback window, in minutes, used to compute the operating-band severity.",
        examples=[60],
    ),
    failure_rate_threshold: Decimal = Query(
        default=Decimal("0.03"),
        ge=0,
        le=1,
        description="Failure-rate threshold used by the operating-band classifier.",
        examples=["0.03"],
    ),
    queue_latency_threshold_seconds: float = Query(
        default=5.0,
        ge=0.1,
        le=600,
        description="Queue-latency threshold, in seconds, used by the operating-band classifier.",
        examples=[5.0],
    ),
    backlog_age_threshold_seconds: float = Query(
        default=300,
        ge=1,
        le=86400,
        description="Backlog-age threshold, in seconds, used by the operating-band classifier.",
        examples=[300.0],
    ),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    return await ingestion_job_service.get_operating_band(
        lookback_minutes=lookback_minutes,
        failure_rate_threshold=failure_rate_threshold,
        queue_latency_threshold_seconds=queue_latency_threshold_seconds,
        backlog_age_threshold_seconds=backlog_age_threshold_seconds,
    )


@router.get(
    "/ingestion/health/policy",
    response_model=IngestionOpsPolicyResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="Get ingestion operating policy thresholds",
    description=(
        "What: Return active ingestion policy thresholds and replay/DLQ guardrails.\n"
        "How: Expose configured defaults used by SLO, operating-band, and replay gating flows.\n"
        "When: Use to prevent config drift and keep runbooks/automation aligned "
        "with runtime policy."
    ),
    responses={
        status.HTTP_200_OK: {
            "description": "Active ingestion operating policy and replay guardrails.",
            "content": {"application/json": {"example": INGESTION_OPS_POLICY_RESPONSE_EXAMPLE}},
        }
    },
)
async def get_ingestion_operating_policy(
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    return await ingestion_job_service.get_operating_policy()


@router.get(
    "/ingestion/health/reprocessing-queue",
    response_model=IngestionReprocessingQueueHealthResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="Get reprocessing queue health by job type",
    description=(
        "What: Return pending/processing/failed reprocessing queue health grouped by job type.\n"
        "How: Aggregate durable reprocessing job states and compute oldest pending age signal.\n"
        "When: Use for operations triage and replay worker scaling decisions."
    ),
    responses={
        status.HTTP_200_OK: {
            "description": "Reprocessing queue health totals and per-job-type rows.",
            "content": {
                "application/json": {
                    "example": INGESTION_REPROCESSING_QUEUE_HEALTH_RESPONSE_EXAMPLE
                }
            },
        }
    },
)
async def get_reprocessing_queue_health(
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    return await ingestion_job_service.get_reprocessing_queue_health()


@router.get(
    "/ingestion/health/capacity",
    response_model=IngestionCapacityStatusResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="Get ingestion capacity and saturation diagnostics",
    description=(
        "What: Return per endpoint/entity ingestion capacity diagnostics using "
        "RFC-065 throughput signals.\n"
        "How: Aggregate accepted, processed, and backlog records and derive "
        "lambda_in, mu_msg, rho, headroom, and drain time.\n"
        "When: Use to detect overload, prioritize scaling, and estimate backlog recovery time."
    ),
    responses={
        status.HTTP_200_OK: {
            "description": "Per endpoint/entity capacity totals and saturation diagnostics.",
            "content": {
                "application/json": {"example": INGESTION_CAPACITY_STATUS_RESPONSE_EXAMPLE}
            },
        }
    },
)
async def get_ingestion_capacity_status(
    lookback_minutes: int = Query(
        default=60,
        ge=5,
        le=1440,
        description="Lookback window, in minutes, used for throughput and saturation metrics.",
        examples=[60],
    ),
    limit: int = Query(
        default=200,
        ge=1,
        le=500,
        description="Maximum number of endpoint/entity capacity rows to return.",
        examples=[200],
    ),
    assumed_replicas: int = Query(
        default=1,
        ge=1,
        le=500,
        description="Replica count assumption used when projecting effective processing capacity.",
        examples=[1],
    ),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    return await ingestion_job_service.get_capacity_status(
        lookback_minutes=lookback_minutes,
        limit=limit,
        assumed_replicas=assumed_replicas,
    )


@router.get(
    "/ingestion/health/backlog-breakdown",
    response_model=IngestionBacklogBreakdownResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="Get ingestion backlog breakdown by endpoint and entity",
    description=(
        "What: Return grouped backlog/failure-rate metrics by endpoint and entity type.\n"
        "How: Aggregate canonical ingestion jobs into endpoint/entity groups "
        "with oldest backlog age.\n"
        "When: Use to isolate the highest-impact ingestion pipeline segment during incidents."
    ),
    responses={
        status.HTTP_200_OK: {
            "description": "Grouped backlog pressure and concentration diagnostics.",
            "content": {
                "application/json": {"example": INGESTION_BACKLOG_BREAKDOWN_RESPONSE_EXAMPLE}
            },
        }
    },
)
async def get_ingestion_backlog_breakdown(
    lookback_minutes: int = Query(
        default=1440,
        ge=5,
        le=10080,
        description="Lookback window, in minutes, used to assemble backlog breakdown metrics.",
        examples=[1440],
    ),
    limit: int = Query(
        default=200,
        ge=1,
        le=500,
        description="Maximum number of backlog rows to return.",
        examples=[200],
    ),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    return await ingestion_job_service.get_backlog_breakdown(
        lookback_minutes=lookback_minutes,
        limit=limit,
    )


@router.get(
    "/ingestion/health/stalled-jobs",
    response_model=IngestionStalledJobListResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="List stalled ingestion jobs",
    description=(
        "What: List ingestion jobs stalled in accepted/queued state beyond threshold.\n"
        "How: Filter canonical jobs by age and status, then attach runbook-oriented suggestions.\n"
        "When: Use to identify concrete stuck jobs requiring operator intervention."
    ),
    responses={
        200: {
            "description": "Stalled ingestion jobs older than the requested threshold.",
            "content": {
                "application/json": {"example": INGESTION_STALLED_JOB_LIST_RESPONSE_EXAMPLE}
            },
        }
    },
)
async def list_ingestion_stalled_jobs(
    threshold_seconds: int = Query(
        default=300,
        ge=30,
        le=86400,
        description="Minimum age, in seconds, that qualifies a queued/accepted job as stalled.",
        examples=[300],
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
        description="Maximum number of stalled jobs to return.",
        examples=[100],
    ),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    return await ingestion_job_service.list_stalled_jobs(
        threshold_seconds=threshold_seconds,
        limit=limit,
    )


@router.get(
    "/ingestion/dlq/consumer-events",
    response_model=ConsumerDlqEventListResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="List consumer dead-letter events",
    description=(
        "What: Return dead-letter events produced by downstream consumers.\n"
        "How: Query persisted consumer DLQ audit records with optional topic/group filters.\n"
        "When: Use to investigate consumer-side validation/processing failures without DB access."
    ),
    responses={
        200: {
            "description": "Consumer DLQ events matching the requested filters.",
            "content": {"application/json": {"example": CONSUMER_DLQ_EVENT_LIST_RESPONSE_EXAMPLE}},
        }
    },
)
async def list_consumer_dlq_events(
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
        description="Maximum number of consumer DLQ events to return.",
        examples=[100],
    ),
    original_topic: str | None = Query(
        default=None,
        description="Optional original Kafka topic filter.",
        examples=["transactions.raw.received"],
    ),
    consumer_group: str | None = Query(
        default=None,
        description="Optional consumer-group filter.",
        examples=["persistence-service-group"],
    ),
    query_service: IngestionOperationsQueryService = Depends(
        get_ingestion_operations_query_service
    ),
):
    page = await query_service.list_consumer_dlq_events(
        limit=limit, original_topic=original_topic, consumer_group=consumer_group
    )
    return ConsumerDlqEventListResponse(events=page.events, total=page.total)


@router.post(
    "/ingestion/dlq/consumer-events/{event_id}/replay",
    response_model=ConsumerDlqReplayResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="Replay ingestion payload for correlated consumer DLQ event",
    description=(
        "What: Replay canonical ingestion payload correlated to a consumer DLQ event.\n"
        "How: Resolve DLQ event -> correlation_id -> ingestion job with durable "
        "payload, then republish.\n"
        "When: Use after fixing downstream consumer defects to recover rejected events safely."
    ),
    responses={
        200: {
            "description": "Replay outcome for the correlated DLQ event.",
            "content": {"application/json": {"example": CONSUMER_DLQ_REPLAY_RESPONSE_EXAMPLE}},
        },
        404: {
            "description": "Consumer DLQ event was not found.",
            "content": {
                "application/json": {"example": INGESTION_CONSUMER_DLQ_EVENT_NOT_FOUND_EXAMPLE}
            },
        },
        500: {
            "description": "Replay audit, publish, or replay bookkeeping failed.",
            "content": {
                "application/json": {
                    "examples": {
                        "replay_audit_write_failed": {
                            "value": INGESTION_REPLAY_AUDIT_WRITE_FAILED_EXAMPLE
                        },
                    }
                }
            },
        },
    },
)
async def replay_consumer_dlq_event(
    event_id: str = Path(
        description="Consumer dead-letter event identifier.",
        examples=["cdlq_01J5VK4Y4EPMTVF1B0HF4CAHB6"],
    ),
    replay_request: ConsumerDlqReplayRequest = Body(
        default_factory=ConsumerDlqReplayRequest,
        openapi_examples=CONSUMER_DLQ_REPLAY_REQUEST_EXAMPLES,
    ),
    ops_actor: str = Depends(require_ops_token),
    command_service: ConsumerDlqReplayCommandService = Depends(
        get_consumer_dlq_replay_command_service
    ),
):
    try:
        result = await command_service.replay_consumer_dlq_event(
            event_id=event_id,
            command=ConsumerDlqReplayCommand(
                dry_run=replay_request.dry_run,
                requested_by=ops_actor,
            ),
        )
    except ReplayCommandError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return ConsumerDlqReplayResponse(**result.to_response_payload())


@router.get(
    "/ingestion/audit/replays",
    response_model=IngestionReplayAuditListResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="List ingestion replay audit records",
    description=(
        "What: Return replay audit records across ingestion recovery paths.\n"
        "How: Query durable replay audit rows with filters for recovery path, "
        "status, fingerprint, and job.\n"
        "When: Use for incident forensics and replay governance review."
    ),
    responses={
        200: {
            "description": "Replay audit rows matching the requested filters.",
            "content": {
                "application/json": {"example": INGESTION_REPLAY_AUDIT_LIST_RESPONSE_EXAMPLE}
            },
        }
    },
)
async def list_ingestion_replay_audits(
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
        description="Maximum number of replay audit rows to return.",
        examples=[100],
    ),
    recovery_path: str | None = Query(
        default=None,
        description="Optional recovery-path filter.",
        examples=["consumer_dlq_replay"],
    ),
    replay_status: str | None = Query(
        default=None,
        description="Optional replay-status filter.",
        examples=["replayed"],
    ),
    replay_fingerprint: str | None = Query(
        default=None,
        description="Optional deterministic replay fingerprint filter.",
        examples=["c5b0faeb7de60bc111f109624e58d0ad6206634be5fef4d4455cdac629df4f3f"],
    ),
    job_id: str | None = Query(
        default=None,
        description="Optional ingestion job identifier filter.",
        examples=["job_01J5S0J6D3BAVMK2E1V0WQ7MCC"],
    ),
    query_service: IngestionOperationsQueryService = Depends(
        get_ingestion_operations_query_service
    ),
):
    page = await query_service.list_replay_audits(
        limit=limit,
        recovery_path=recovery_path,
        replay_status=replay_status,
        replay_fingerprint=replay_fingerprint,
        job_id=job_id,
    )
    return IngestionReplayAuditListResponse(audits=page.audits, total=page.total)


@router.get(
    "/ingestion/audit/replays/{replay_id}",
    response_model=IngestionReplayAuditResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="Get one ingestion replay audit record",
    description=(
        "What: Return one replay audit row by replay_id.\n"
        "How: Read durable replay audit event from canonical operations store.\n"
        "When: Use to inspect a specific replay action referenced in incident timelines."
    ),
    responses={
        200: {
            "description": "One replay audit row.",
            "content": {"application/json": {"example": INGESTION_REPLAY_AUDIT_RESPONSE_EXAMPLE}},
        },
        404: {
            "description": "Replay audit row was not found.",
            "content": {"application/json": {"example": INGESTION_REPLAY_AUDIT_NOT_FOUND_EXAMPLE}},
        },
    },
)
async def get_ingestion_replay_audit(
    replay_id: str = Path(
        description="Replay audit identifier.",
        examples=["replay_01J5WK1G7S3HBQ7Q3M0E3TMT0P"],
    ),
    query_service: IngestionOperationsQueryService = Depends(
        get_ingestion_operations_query_service
    ),
):
    try:
        return await query_service.get_replay_audit(replay_id)
    except IngestionOperationsNotFound as exc:
        raise _not_found_response(exc) from exc


@router.get(
    "/ingestion/ops/control",
    response_model=IngestionOpsModeResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="Get ingestion operations control mode",
    description=(
        "What: Return current ingestion control mode and replay window.\n"
        "How: Read canonical ingestion operations control state.\n"
        "When: Use before maintenance, pause/drain actions, or controlled replay operations."
    ),
    responses={
        200: {
            "description": "Current ingestion operations mode.",
            "content": {"application/json": {"example": INGESTION_OPS_MODE_EXAMPLE}},
        }
    },
)
async def get_ingestion_ops_control(
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    return await ingestion_job_service.get_ops_mode()


@router.put(
    "/ingestion/ops/control",
    response_model=IngestionOpsModeResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="Update ingestion operations control mode",
    description=(
        "What: Update ingestion control mode and optional replay window.\n"
        "How: Persist operational mode transition with validation on replay window boundaries.\n"
        "When: Use for planned maintenance, controlled drain, or replay governance actions."
    ),
    responses={
        200: {
            "description": "Updated ingestion operations mode.",
            "content": {"application/json": {"example": INGESTION_OPS_MODE_EXAMPLE}},
        }
    },
)
async def update_ingestion_ops_control(
    update_request: IngestionOpsModeUpdateRequest = Body(
        openapi_examples={
            "pause_with_window": {
                "summary": "Pause ingestion with bounded replay window",
                "value": {
                    "mode": "paused",
                    "replay_window_start": "2026-03-06T00:00:00Z",
                    "replay_window_end": "2026-03-06T06:00:00Z",
                    "updated_by": "ops_automation",
                },
            }
        }
    ),
    command_service: OpsControlCommandService = Depends(get_ops_control_command_service),
):
    try:
        return await command_service.update_ingestion_ops_control(
            OpsControlUpdateCommand(
                mode=update_request.mode,
                replay_window_start=update_request.replay_window_start,
                replay_window_end=update_request.replay_window_end,
                updated_by=update_request.updated_by,
            )
        )
    except OpsControlCommandError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get(
    "/ingestion/idempotency/diagnostics",
    response_model=IngestionIdempotencyDiagnosticsResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="Get idempotency key diagnostics",
    description=(
        "What: Return operational diagnostics for ingestion idempotency key reuse and collisions.\n"
        "How: Aggregate ingestion jobs by idempotency key and detect multi-endpoint collisions.\n"
        "When: Use to detect client integration anti-patterns before they create replay ambiguity."
    ),
    responses={
        200: {
            "description": "Idempotency-key diagnostics for the requested lookback window.",
            "content": {
                "application/json": {"example": INGESTION_IDEMPOTENCY_DIAGNOSTICS_RESPONSE_EXAMPLE}
            },
        }
    },
)
async def get_ingestion_idempotency_diagnostics(
    lookback_minutes: int = Query(
        default=1440,
        ge=5,
        le=10080,
        description="Lookback window, in minutes, used to aggregate idempotency-key behavior.",
        examples=[1440],
    ),
    limit: int = Query(
        default=200,
        ge=1,
        le=500,
        description="Maximum number of idempotency diagnostics rows to return.",
        examples=[200],
    ),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    return await ingestion_job_service.get_idempotency_diagnostics(
        lookback_minutes=lookback_minutes,
        limit=limit,
    )
