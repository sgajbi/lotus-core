import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer

from src.services.ingestion_service.app.DTOs.business_date_dto import BusinessDateIngestionRequest
from src.services.ingestion_service.app.DTOs.fx_rate_dto import FxRateIngestionRequest
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
    IngestionJobFailureListResponse,
    IngestionJobListResponse,
    IngestionJobRecordStatusResponse,
    IngestionJobResponse,
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
from src.services.ingestion_service.app.DTOs.instrument_dto import InstrumentIngestionRequest
from src.services.ingestion_service.app.DTOs.market_price_dto import MarketPriceIngestionRequest
from src.services.ingestion_service.app.DTOs.portfolio_bundle_dto import (
    PortfolioBundleIngestionRequest,
)
from src.services.ingestion_service.app.DTOs.portfolio_dto import PortfolioIngestionRequest
from src.services.ingestion_service.app.DTOs.reprocessing_dto import ReprocessingRequest
from src.services.ingestion_service.app.DTOs.transaction_dto import TransactionIngestionRequest
from src.services.ingestion_service.app.ops_controls import require_ops_token
from src.services.ingestion_service.app.request_metadata import get_request_lineage
from src.services.ingestion_service.app.routers.reprocessing import REPROCESSING_REQUESTED_TOPIC
from src.services.ingestion_service.app.services.ingestion_job_service import (
    IngestionJobService,
    get_ingestion_job_service,
)
from src.services.ingestion_service.app.services.ingestion_service import (
    IngestionService,
    get_ingestion_service,
)

router = APIRouter(dependencies=[Depends(require_ops_token)])


def _filter_payload_by_record_keys(
    *,
    endpoint: str,
    payload: dict[str, Any],
    record_keys: list[str],
) -> dict[str, Any]:
    if not record_keys:
        return payload
    key_set = set(record_keys)
    if endpoint == "/ingest/transactions":
        rows = [
            row for row in payload.get("transactions", []) if row.get("transaction_id") in key_set
        ]
        return {"transactions": rows}
    if endpoint == "/ingest/portfolios":
        rows = [row for row in payload.get("portfolios", []) if row.get("portfolio_id") in key_set]
        return {"portfolios": rows}
    if endpoint == "/ingest/instruments":
        rows = [row for row in payload.get("instruments", []) if row.get("security_id") in key_set]
        return {"instruments": rows}
    if endpoint == "/ingest/business-dates":
        rows = [
            row
            for row in payload.get("business_dates", [])
            if str(row.get("business_date")) in key_set
        ]
        return {"business_dates": rows}
    if endpoint == "/reprocess/transactions":
        rows = [txn_id for txn_id in payload.get("transaction_ids", []) if txn_id in key_set]
        return {"transaction_ids": rows}
    raise ValueError(f"Partial retry is not supported for endpoint '{endpoint}'.")


async def _replay_job_payload(
    *,
    endpoint: str,
    payload: dict[str, Any],
    idempotency_key: str | None,
    ingestion_service: IngestionService,
    kafka_producer: KafkaProducer,
) -> None:
    if endpoint == "/ingest/transactions":
        request_model = TransactionIngestionRequest.model_validate(payload)
        await ingestion_service.publish_transactions(
            request_model.transactions, idempotency_key=idempotency_key
        )
        return
    if endpoint == "/ingest/portfolios":
        request_model = PortfolioIngestionRequest.model_validate(payload)
        await ingestion_service.publish_portfolios(
            request_model.portfolios, idempotency_key=idempotency_key
        )
        return
    if endpoint == "/ingest/instruments":
        request_model = InstrumentIngestionRequest.model_validate(payload)
        await ingestion_service.publish_instruments(
            request_model.instruments, idempotency_key=idempotency_key
        )
        return
    if endpoint == "/ingest/market-prices":
        request_model = MarketPriceIngestionRequest.model_validate(payload)
        await ingestion_service.publish_market_prices(
            request_model.market_prices, idempotency_key=idempotency_key
        )
        return
    if endpoint == "/ingest/fx-rates":
        request_model = FxRateIngestionRequest.model_validate(payload)
        await ingestion_service.publish_fx_rates(
            request_model.fx_rates, idempotency_key=idempotency_key
        )
        return
    if endpoint == "/ingest/business-dates":
        request_model = BusinessDateIngestionRequest.model_validate(payload)
        await ingestion_service.publish_business_dates(
            request_model.business_dates, idempotency_key=idempotency_key
        )
        return
    if endpoint == "/ingest/portfolio-bundle":
        request_model = PortfolioBundleIngestionRequest.model_validate(payload)
        await ingestion_service.publish_portfolio_bundle(
            request_model, idempotency_key=idempotency_key
        )
        return
    if endpoint == "/reprocess/transactions":
        request_model = ReprocessingRequest.model_validate(payload)
        correlation_id, _, _ = get_request_lineage()
        headers: list[tuple[str, bytes]] = []
        if correlation_id:
            headers.append(("correlation_id", correlation_id.encode("utf-8")))
        if idempotency_key:
            headers.append(("idempotency_key", idempotency_key.encode("utf-8")))
        for txn_id in request_model.transaction_ids:
            kafka_producer.publish_message(
                topic=REPROCESSING_REQUESTED_TOPIC,
                key=txn_id,
                value={"transaction_id": txn_id},
                headers=headers or None,
            )
        kafka_producer.flush(timeout=5)
        return
    raise ValueError(f"Retry not supported for endpoint '{endpoint}'.")


def _deterministic_replay_fingerprint(
    *,
    event_id: str,
    correlation_id: str | None,
    job_id: str | None,
    endpoint: str | None,
    payload: dict[str, Any] | None,
    idempotency_key: str | None,
) -> str:
    basis = {
        "event_id": event_id,
        "correlation_id": correlation_id,
        "job_id": job_id,
        "endpoint": endpoint,
        "idempotency_key": idempotency_key,
        "payload": payload or {},
    }
    canonical = json.dumps(basis, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _payload_record_count(payload: dict[str, Any] | None) -> int:
    if not payload:
        return 0
    counts = [len(value) for value in payload.values() if isinstance(value, list)]
    if counts:
        return max(counts)
    return 1


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
)
async def get_ingestion_job(
    job_id: str,
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
)
async def list_ingestion_jobs(
    status: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    submitted_from: datetime | None = Query(default=None),
    submitted_to: datetime | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    status_value = status if status in {"accepted", "queued", "failed"} else None
    jobs, next_cursor = await ingestion_job_service.list_jobs(
        status=status_value,
        entity_type=entity_type,
        submitted_from=submitted_from,
        submitted_to=submitted_to,
        cursor=cursor,
        limit=limit,
    )
    return IngestionJobListResponse(jobs=jobs, total=len(jobs), next_cursor=next_cursor)


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
)
async def list_ingestion_job_failures(
    job_id: str,
    limit: int = Query(default=100, ge=1, le=500),
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
    failures = await ingestion_job_service.list_failures(job_id=job_id, limit=limit)
    return IngestionJobFailureListResponse(failures=failures, total=len(failures))


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
)
async def get_ingestion_job_records(
    job_id: str,
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    record_status = await ingestion_job_service.get_job_record_status(job_id)
    if record_status is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "INGESTION_JOB_NOT_FOUND",
                "message": f"Ingestion job '{job_id}' was not found.",
            },
        )
    return record_status


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
)
async def retry_ingestion_job(
    job_id: str,
    retry_request: IngestionRetryRequest = Body(default_factory=IngestionRetryRequest),
    ops_actor: str = Depends(require_ops_token),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
    kafka_producer: KafkaProducer = Depends(get_kafka_producer),
):
    context = await ingestion_job_service.get_job_replay_context(job_id)
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "INGESTION_JOB_NOT_FOUND",
                "message": f"Ingestion job '{job_id}' was not found.",
            },
        )
    if context.request_payload is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "INGESTION_JOB_RETRY_UNSUPPORTED",
                "message": (
                    f"Ingestion job '{job_id}' does not have stored request payload and "
                    "cannot be retried."
                ),
            },
        )
    try:
        replay_payload = _filter_payload_by_record_keys(
            endpoint=context.endpoint,
            payload=context.request_payload,
            record_keys=retry_request.record_keys,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "INGESTION_PARTIAL_RETRY_UNSUPPORTED", "message": str(exc)},
        ) from exc
    replay_record_count = _payload_record_count(replay_payload)
    try:
        await ingestion_job_service.assert_retry_allowed_for_records(
            submitted_at=context.submitted_at,
            replay_record_count=replay_record_count,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "INGESTION_RETRY_BLOCKED", "message": str(exc)},
        ) from exc

    if retry_request.dry_run:
        replay_fingerprint = _deterministic_replay_fingerprint(
            event_id=f"job:{job_id}",
            correlation_id=None,
            job_id=job_id,
            endpoint=context.endpoint,
            payload=replay_payload,
            idempotency_key=context.idempotency_key,
        )
        await ingestion_job_service.record_consumer_dlq_replay_audit(
            recovery_path="ingestion_job_retry",
            event_id=f"job:{job_id}",
            replay_fingerprint=replay_fingerprint,
            correlation_id=None,
            job_id=job_id,
            endpoint=context.endpoint,
            replay_status="dry_run",
            dry_run=True,
            replay_reason="Dry-run successful. Ingestion job retry is replayable.",
            requested_by=ops_actor,
        )
        job = await ingestion_job_service.get_job(job_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "INGESTION_JOB_NOT_FOUND",
                    "message": f"Ingestion job '{job_id}' was not found after dry-run.",
                },
            )
        return job

    replay_fingerprint = _deterministic_replay_fingerprint(
        event_id=f"job:{job_id}",
        correlation_id=None,
        job_id=job_id,
        endpoint=context.endpoint,
        payload=replay_payload,
        idempotency_key=context.idempotency_key,
    )
    existing_success = await ingestion_job_service.find_successful_replay_audit_by_fingerprint(
        replay_fingerprint=replay_fingerprint,
        recovery_path="ingestion_job_retry",
    )
    if existing_success:
        await ingestion_job_service.record_consumer_dlq_replay_audit(
            recovery_path="ingestion_job_retry",
            event_id=f"job:{job_id}",
            replay_fingerprint=replay_fingerprint,
            correlation_id=None,
            job_id=job_id,
            endpoint=context.endpoint,
            replay_status="duplicate_blocked",
            dry_run=False,
            replay_reason=(
                "Retry blocked because this deterministic retry fingerprint was already replayed "
                f"successfully (replay_id={existing_success['replay_id']})."
            ),
            requested_by=ops_actor,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "INGESTION_RETRY_DUPLICATE_BLOCKED",
                "message": (
                    "Retry blocked because an equivalent deterministic replay "
                    "already succeeded."
                ),
                "replay_fingerprint": replay_fingerprint,
            },
        )

    try:
        await _replay_job_payload(
            endpoint=context.endpoint,
            payload=replay_payload,
            idempotency_key=context.idempotency_key,
            ingestion_service=ingestion_service,
            kafka_producer=kafka_producer,
        )
        await ingestion_job_service.mark_retried(job_id)
        await ingestion_job_service.mark_queued(job_id)
        await ingestion_job_service.record_consumer_dlq_replay_audit(
            recovery_path="ingestion_job_retry",
            event_id=f"job:{job_id}",
            replay_fingerprint=replay_fingerprint,
            correlation_id=None,
            job_id=job_id,
            endpoint=context.endpoint,
            replay_status="replayed",
            dry_run=False,
            replay_reason="Ingestion job retry replay succeeded.",
            requested_by=ops_actor,
        )
    except Exception as exc:
        await ingestion_job_service.record_consumer_dlq_replay_audit(
            recovery_path="ingestion_job_retry",
            event_id=f"job:{job_id}",
            replay_fingerprint=replay_fingerprint,
            correlation_id=None,
            job_id=job_id,
            endpoint=context.endpoint,
            replay_status="failed",
            dry_run=False,
            replay_reason=str(exc),
            requested_by=ops_actor,
        )
        await ingestion_job_service.mark_failed(
            job_id,
            str(exc),
            failure_phase="retry_publish",
            failed_record_keys=retry_request.record_keys,
        )
        raise

    job = await ingestion_job_service.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "INGESTION_JOB_NOT_FOUND",
                "message": f"Ingestion job '{job_id}' was not found after retry.",
            },
        )
    return job


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
)
async def get_ingestion_consumer_lag(
    lookback_minutes: int = Query(default=60, ge=5, le=1440),
    limit: int = Query(default=100, ge=1, le=500),
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
)
async def get_ingestion_slo_status(
    lookback_minutes: int = Query(default=60, ge=5, le=1440),
    failure_rate_threshold: Decimal = Query(default=Decimal("0.03"), ge=0, le=1),
    queue_latency_threshold_seconds: float = Query(default=5.0, ge=0.1, le=600),
    backlog_age_threshold_seconds: float = Query(default=300, ge=1, le=86400),
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
)
async def get_ingestion_error_budget_status(
    lookback_minutes: int = Query(default=60, ge=5, le=1440),
    failure_rate_threshold: Decimal = Query(default=Decimal("0.03"), ge=0, le=1),
    backlog_growth_threshold: int = Query(default=5, ge=0, le=10000),
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
)
async def get_ingestion_operating_band(
    lookback_minutes: int = Query(default=60, ge=5, le=1440),
    failure_rate_threshold: Decimal = Query(default=Decimal("0.03"), ge=0, le=1),
    queue_latency_threshold_seconds: float = Query(default=5.0, ge=0.1, le=600),
    backlog_age_threshold_seconds: float = Query(default=300, ge=1, le=86400),
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
)
async def get_ingestion_capacity_status(
    lookback_minutes: int = Query(default=60, ge=5, le=1440),
    limit: int = Query(default=200, ge=1, le=500),
    assumed_replicas: int = Query(default=1, ge=1, le=500),
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
)
async def get_ingestion_backlog_breakdown(
    lookback_minutes: int = Query(default=1440, ge=5, le=10080),
    limit: int = Query(default=200, ge=1, le=500),
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
)
async def list_ingestion_stalled_jobs(
    threshold_seconds: int = Query(default=300, ge=30, le=86400),
    limit: int = Query(default=100, ge=1, le=500),
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
)
async def list_consumer_dlq_events(
    limit: int = Query(default=100, ge=1, le=500),
    original_topic: str | None = Query(default=None),
    consumer_group: str | None = Query(default=None),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    events = await ingestion_job_service.list_consumer_dlq_events(
        limit=limit, original_topic=original_topic, consumer_group=consumer_group
    )
    return ConsumerDlqEventListResponse(events=events, total=len(events))


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
)
async def replay_consumer_dlq_event(
    event_id: str,
    replay_request: ConsumerDlqReplayRequest = Body(default_factory=ConsumerDlqReplayRequest),
    ops_actor: str = Depends(require_ops_token),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
    kafka_producer: KafkaProducer = Depends(get_kafka_producer),
):
    event = await ingestion_job_service.get_consumer_dlq_event(event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "INGESTION_CONSUMER_DLQ_EVENT_NOT_FOUND",
                "message": f"Consumer DLQ event '{event_id}' was not found.",
            },
        )
    if not event.correlation_id:
        replay_fingerprint = _deterministic_replay_fingerprint(
            event_id=event_id,
            correlation_id=None,
            job_id=None,
            endpoint=None,
            payload=None,
            idempotency_key=None,
        )
        replay_audit_id = await ingestion_job_service.record_consumer_dlq_replay_audit(
            recovery_path="consumer_dlq_replay",
            event_id=event_id,
            replay_fingerprint=replay_fingerprint,
            correlation_id=None,
            job_id=None,
            endpoint=None,
            replay_status="not_replayable",
            dry_run=replay_request.dry_run,
            replay_reason=(
                "DLQ event has no correlation id and cannot be mapped to "
                "ingestion payload."
            ),
            requested_by=ops_actor,
        )
        return ConsumerDlqReplayResponse(
            event_id=event_id,
            correlation_id=None,
            job_id=None,
            replay_status="not_replayable",
            replay_audit_id=replay_audit_id,
            replay_fingerprint=replay_fingerprint,
            message="DLQ event has no correlation id and cannot be mapped to ingestion payload.",
        )

    jobs, _ = await ingestion_job_service.list_jobs(limit=500)

    def _job_field(job: Any, field: str) -> Any:
        if isinstance(job, dict):
            return job.get(field)
        return getattr(job, field, None)

    replay_job = next(
        (
            job
            for job in jobs
            if _job_field(job, "correlation_id") == event.correlation_id
            and _job_field(job, "status") in {"failed", "queued", "accepted"}
        ),
        None,
    )
    if replay_job is None:
        replay_fingerprint = _deterministic_replay_fingerprint(
            event_id=event_id,
            correlation_id=event.correlation_id,
            job_id=None,
            endpoint=None,
            payload=None,
            idempotency_key=None,
        )
        replay_audit_id = await ingestion_job_service.record_consumer_dlq_replay_audit(
            recovery_path="consumer_dlq_replay",
            event_id=event_id,
            replay_fingerprint=replay_fingerprint,
            correlation_id=event.correlation_id,
            job_id=None,
            endpoint=None,
            replay_status="not_replayable",
            dry_run=replay_request.dry_run,
            replay_reason="No correlated ingestion job found for consumer DLQ event.",
            requested_by=ops_actor,
        )
        return ConsumerDlqReplayResponse(
            event_id=event_id,
            correlation_id=event.correlation_id,
            job_id=None,
            replay_status="not_replayable",
            replay_audit_id=replay_audit_id,
            replay_fingerprint=replay_fingerprint,
            message="No correlated ingestion job found for consumer DLQ event.",
        )

    replay_job_id = str(_job_field(replay_job, "job_id"))
    context = await ingestion_job_service.get_job_replay_context(replay_job_id)
    replay_fingerprint = _deterministic_replay_fingerprint(
        event_id=event_id,
        correlation_id=event.correlation_id,
        job_id=replay_job_id,
        endpoint=context.endpoint if context else None,
        payload=context.request_payload if context else None,
        idempotency_key=context.idempotency_key if context else None,
    )
    if context is None or context.request_payload is None:
        replay_audit_id = await ingestion_job_service.record_consumer_dlq_replay_audit(
            recovery_path="consumer_dlq_replay",
            event_id=event_id,
            replay_fingerprint=replay_fingerprint,
            correlation_id=event.correlation_id,
            job_id=replay_job_id,
            endpoint=context.endpoint if context else None,
            replay_status="not_replayable",
            dry_run=replay_request.dry_run,
            replay_reason="Correlated ingestion job does not have durable replay payload.",
            requested_by=ops_actor,
        )
        return ConsumerDlqReplayResponse(
            event_id=event_id,
            correlation_id=event.correlation_id,
            job_id=replay_job_id,
            replay_status="not_replayable",
            replay_audit_id=replay_audit_id,
            replay_fingerprint=replay_fingerprint,
            message="Correlated ingestion job does not have durable replay payload.",
        )
    existing_success = await ingestion_job_service.find_successful_replay_audit_by_fingerprint(
        replay_fingerprint,
        recovery_path="consumer_dlq_replay",
    )
    if existing_success and not replay_request.dry_run:
        replay_audit_id = await ingestion_job_service.record_consumer_dlq_replay_audit(
            recovery_path="consumer_dlq_replay",
            event_id=event_id,
            replay_fingerprint=replay_fingerprint,
            correlation_id=event.correlation_id,
            job_id=replay_job_id,
            endpoint=context.endpoint,
            replay_status="duplicate_blocked",
            dry_run=False,
            replay_reason=(
                "Replay blocked because this deterministic replay fingerprint was already replayed "
                f"successfully (replay_id={existing_success['replay_id']})."
            ),
            requested_by=ops_actor,
        )
        return ConsumerDlqReplayResponse(
            event_id=event_id,
            correlation_id=event.correlation_id,
            job_id=replay_job_id,
            replay_status="duplicate_blocked",
            replay_audit_id=replay_audit_id,
            replay_fingerprint=replay_fingerprint,
            message=(
                "Replay blocked because an equivalent deterministic replay already succeeded."
            ),
        )
    await ingestion_job_service.assert_retry_allowed_for_records(
        submitted_at=context.submitted_at,
        replay_record_count=_payload_record_count(context.request_payload),
    )
    if replay_request.dry_run:
        replay_audit_id = await ingestion_job_service.record_consumer_dlq_replay_audit(
            recovery_path="consumer_dlq_replay",
            event_id=event_id,
            replay_fingerprint=replay_fingerprint,
            correlation_id=event.correlation_id,
            job_id=replay_job_id,
            endpoint=context.endpoint,
            replay_status="dry_run",
            dry_run=True,
            replay_reason="Dry-run successful. Correlated ingestion job is replayable.",
            requested_by=ops_actor,
        )
        return ConsumerDlqReplayResponse(
            event_id=event_id,
            correlation_id=event.correlation_id,
            job_id=replay_job_id,
            replay_status="dry_run",
            replay_audit_id=replay_audit_id,
            replay_fingerprint=replay_fingerprint,
            message="Dry-run successful. Correlated ingestion job is replayable.",
        )
    try:
        await _replay_job_payload(
            endpoint=context.endpoint,
            payload=context.request_payload,
            idempotency_key=context.idempotency_key,
            ingestion_service=ingestion_service,
            kafka_producer=kafka_producer,
        )
        await ingestion_job_service.mark_retried(replay_job_id)
        await ingestion_job_service.mark_queued(replay_job_id)
        replay_audit_id = await ingestion_job_service.record_consumer_dlq_replay_audit(
            recovery_path="consumer_dlq_replay",
            event_id=event_id,
            replay_fingerprint=replay_fingerprint,
            correlation_id=event.correlation_id,
            job_id=replay_job_id,
            endpoint=context.endpoint,
            replay_status="replayed",
            dry_run=False,
            replay_reason="Replayed ingestion job from correlated consumer DLQ event.",
            requested_by=ops_actor,
        )
    except Exception as exc:
        replay_audit_id = await ingestion_job_service.record_consumer_dlq_replay_audit(
            recovery_path="consumer_dlq_replay",
            event_id=event_id,
            replay_fingerprint=replay_fingerprint,
            correlation_id=event.correlation_id,
            job_id=replay_job_id,
            endpoint=context.endpoint,
            replay_status="failed",
            dry_run=False,
            replay_reason=str(exc),
            requested_by=ops_actor,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INGESTION_DLQ_REPLAY_FAILED",
                "message": str(exc),
                "replay_audit_id": replay_audit_id,
            },
        ) from exc
    return ConsumerDlqReplayResponse(
        event_id=event_id,
        correlation_id=event.correlation_id,
        job_id=replay_job_id,
        replay_status="replayed",
        replay_audit_id=replay_audit_id,
        replay_fingerprint=replay_fingerprint,
        message="Replayed ingestion job from correlated consumer DLQ event.",
    )


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
)
async def list_ingestion_replay_audits(
    limit: int = Query(default=100, ge=1, le=500),
    recovery_path: str | None = Query(default=None),
    replay_status: str | None = Query(default=None),
    replay_fingerprint: str | None = Query(default=None),
    job_id: str | None = Query(default=None),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    audits = await ingestion_job_service.list_replay_audits(
        limit=limit,
        recovery_path=recovery_path,
        replay_status=replay_status,
        replay_fingerprint=replay_fingerprint,
        job_id=job_id,
    )
    return IngestionReplayAuditListResponse(audits=audits, total=len(audits))


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
)
async def get_ingestion_replay_audit(
    replay_id: str,
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    audit = await ingestion_job_service.get_replay_audit(replay_id)
    if audit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "INGESTION_REPLAY_AUDIT_NOT_FOUND",
                "message": f"Replay audit '{replay_id}' was not found.",
            },
        )
    return audit


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
)
async def update_ingestion_ops_control(
    update_request: IngestionOpsModeUpdateRequest,
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    if (
        update_request.replay_window_start
        and update_request.replay_window_end
        and update_request.replay_window_start > update_request.replay_window_end
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INGESTION_INVALID_REPLAY_WINDOW",
                "message": "replay_window_start must be before replay_window_end.",
            },
        )
    return await ingestion_job_service.update_ops_mode(
        mode=update_request.mode,
        replay_window_start=update_request.replay_window_start,
        replay_window_end=update_request.replay_window_end,
        updated_by=update_request.updated_by,
    )


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
)
async def get_ingestion_idempotency_diagnostics(
    lookback_minutes: int = Query(default=1440, ge=5, le=10080),
    limit: int = Query(default=200, ge=1, le=500),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    return await ingestion_job_service.get_idempotency_diagnostics(
        lookback_minutes=lookback_minutes,
        limit=limit,
    )
