import hashlib
import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, status
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
from src.services.ingestion_service.app.DTOs.instrument_dto import InstrumentIngestionRequest
from src.services.ingestion_service.app.DTOs.market_price_dto import MarketPriceIngestionRequest
from src.services.ingestion_service.app.DTOs.portfolio_bundle_dto import (
    PortfolioBundleIngestionRequest,
)
from src.services.ingestion_service.app.DTOs.portfolio_dto import PortfolioIngestionRequest
from src.services.ingestion_service.app.DTOs.reprocessing_dto import ReprocessingRequest
from src.services.ingestion_service.app.DTOs.transaction_dto import TransactionIngestionRequest
from src.services.ingestion_service.app.ops_controls import require_ops_token
from src.services.ingestion_service.app.services.ingestion_job_service import (
    IngestionJobService,
    get_ingestion_job_service,
)
from src.services.ingestion_service.app.services.ingestion_service import (
    IngestionService,
    get_ingestion_service,
)

router = APIRouter(dependencies=[Depends(require_ops_token)])
logger = logging.getLogger(__name__)

INGESTION_JOB_RESPONSE_EXAMPLE = {
    "job_id": "job_01J5S0J6D3BAVMK2E1V0WQ7MCC",
    "endpoint": "/ingest/transactions",
    "entity_type": "transaction",
    "status": "queued",
    "accepted_count": 125,
    "idempotency_key": "ingestion-transactions-batch-20260306-001",
    "correlation_id": "ING:7f4a64b0-35f4-41bc-8f74-cb556f2ad9a3",
    "request_id": "REQ:3a63936e-bf29-41e2-9f16-faf4e561d845",
    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
    "submitted_at": "2026-03-06T13:22:24.201Z",
    "completed_at": "2026-03-06T13:22:24.994Z",
    "failure_reason": None,
    "retry_count": 1,
    "last_retried_at": "2026-03-06T13:24:10.512Z",
}

INGESTION_JOB_FAILURE_LIST_RESPONSE_EXAMPLE = {
    "failures": [
        {
            "failure_id": "fail_01J5S27P16BSKQ3R2P2HK67GQZ",
            "job_id": "job_01J5S0J6D3BAVMK2E1V0WQ7MCC",
            "failure_phase": "publish",
            "failure_reason": "Kafka publish timeout for topic transactions.raw.received.",
            "failed_record_keys": ["TXN-2026-000145", "TXN-2026-000146"],
            "failed_at": "2026-03-06T13:23:09.021Z",
        }
    ],
    "total": 1,
}

INGESTION_JOB_RECORD_STATUS_RESPONSE_EXAMPLE = {
    "job_id": "job_01J5S0J6D3BAVMK2E1V0WQ7MCC",
    "entity_type": "transaction",
    "accepted_count": 3,
    "failed_record_keys": ["TXN-2026-000145", "TXN-2026-000146"],
    "replayable_record_keys": [
        "TXN-2026-000145",
        "TXN-2026-000146",
        "TXN-2026-000147",
    ],
}

INGESTION_HEALTH_SUMMARY_RESPONSE_EXAMPLE = {
    "total_jobs": 2450,
    "accepted_jobs": 3,
    "queued_jobs": 7,
    "failed_jobs": 2,
    "backlog_jobs": 10,
    "oldest_backlog_job_id": "job_01J5S0J6D3BAVMK2E1V0WQ7MCC",
}

INGESTION_CONSUMER_LAG_RESPONSE_EXAMPLE = {
    "lookback_minutes": 60,
    "backlog_jobs": 10,
    "total_groups": 2,
    "groups": [
        {
            "consumer_group": "persistence-service-group",
            "original_topic": "transactions.raw.received",
            "dlq_events": 21,
            "last_observed_at": "2026-03-06T13:25:42.501Z",
            "lag_severity": "high",
        },
        {
            "consumer_group": "valuation-service-group",
            "original_topic": "market-prices.raw.received",
            "dlq_events": 8,
            "last_observed_at": "2026-03-06T13:21:18.113Z",
            "lag_severity": "medium",
        },
    ],
}

INGESTION_SLO_STATUS_RESPONSE_EXAMPLE = {
    "lookback_minutes": 60,
    "total_jobs": 320,
    "failed_jobs": 4,
    "failure_rate": "0.0125",
    "p95_queue_latency_seconds": 1.42,
    "backlog_age_seconds": 74.0,
    "breach_failure_rate": False,
    "breach_queue_latency": False,
    "breach_backlog_age": False,
}

INGESTION_ERROR_BUDGET_STATUS_RESPONSE_EXAMPLE = {
    "lookback_minutes": 60,
    "previous_lookback_minutes": 60,
    "total_jobs": 320,
    "failed_jobs": 7,
    "failure_rate": "0.021875",
    "remaining_error_budget": "0.008125",
    "backlog_jobs": 12,
    "previous_backlog_jobs": 9,
    "backlog_growth": 3,
    "replay_backlog_pressure_ratio": "0.0024",
    "dlq_events_in_window": 4,
    "dlq_budget_events_per_window": 10,
    "dlq_pressure_ratio": "0.4000",
    "breach_failure_rate": False,
    "breach_backlog_growth": False,
}

INGESTION_OPERATING_BAND_RESPONSE_EXAMPLE = {
    "lookback_minutes": 60,
    "operating_band": "yellow",
    "recommended_action": "Scale up one band and monitor DLQ pressure.",
    "backlog_age_seconds": 42.0,
    "dlq_pressure_ratio": "0.3000",
    "failure_rate": "0.0125",
    "triggered_signals": ["backlog_age_seconds>=15", "dlq_pressure_ratio>=0.25"],
}

INGESTION_OPS_POLICY_RESPONSE_EXAMPLE = {
    "policy_version": "v1",
    "policy_fingerprint": "e6a9f2cc3bb5e5a7",
    "lookback_minutes_default": 60,
    "failure_rate_threshold_default": "0.03",
    "queue_latency_threshold_seconds_default": 5.0,
    "backlog_age_threshold_seconds_default": 300.0,
    "replay_max_records_per_request": 5000,
    "replay_max_backlog_jobs": 5000,
    "reprocessing_worker_poll_interval_seconds": 10,
    "reprocessing_worker_batch_size": 10,
    "valuation_scheduler_poll_interval_seconds": 30,
    "valuation_scheduler_batch_size": 100,
    "valuation_scheduler_dispatch_rounds": 10,
    "dlq_budget_events_per_window": 10,
    "operating_band_yellow_backlog_age_seconds": 15.0,
    "operating_band_orange_backlog_age_seconds": 60.0,
    "operating_band_red_backlog_age_seconds": 180.0,
    "operating_band_yellow_dlq_pressure_ratio": "0.25",
    "operating_band_orange_dlq_pressure_ratio": "0.50",
    "operating_band_red_dlq_pressure_ratio": "1.0",
    "calculator_peak_lag_age_seconds": {
        "position": 30,
        "cost": 45,
        "valuation": 60,
        "cashflow": 45,
        "timeseries": 120,
    },
    "replay_isolation_mode": "shared_workers",
    "partition_growth_strategy": "scale_out_only",
    "replay_dry_run_supported": True,
}

INGESTION_REPROCESSING_QUEUE_HEALTH_RESPONSE_EXAMPLE = {
    "as_of": "2026-03-03T04:12:20.000Z",
    "total_pending_jobs": 5,
    "total_processing_jobs": 2,
    "total_failed_jobs": 1,
    "queues": [
        {
            "job_type": "RESET_WATERMARKS",
            "pending_jobs": 4,
            "processing_jobs": 1,
            "failed_jobs": 0,
            "oldest_pending_created_at": "2026-03-03T04:10:11.000Z",
            "oldest_pending_age_seconds": 127.5,
        },
        {
            "job_type": "RECALCULATE_POSITIONS",
            "pending_jobs": 1,
            "processing_jobs": 1,
            "failed_jobs": 1,
            "oldest_pending_created_at": "2026-03-03T04:11:03.000Z",
            "oldest_pending_age_seconds": 75.0,
        },
    ],
}

INGESTION_CAPACITY_STATUS_RESPONSE_EXAMPLE = {
    "as_of": "2026-03-03T14:55:22.000Z",
    "lookback_minutes": 60,
    "assumed_replicas": 2,
    "total_backlog_records": 300,
    "total_groups": 1,
    "groups": [
        {
            "endpoint": "/ingest/transactions",
            "entity_type": "transaction",
            "total_records": 1200,
            "processed_records": 900,
            "backlog_records": 300,
            "backlog_jobs": 6,
            "lambda_in_events_per_second": "0.333333",
            "mu_msg_per_replica_events_per_second": "0.250000",
            "assumed_replicas": 2,
            "effective_capacity_events_per_second": "0.500000",
            "utilization_ratio": "0.666666",
            "headroom_ratio": "0.333334",
            "estimated_drain_seconds": 1800.0,
            "saturation_state": "stable",
        }
    ],
}

INGESTION_BACKLOG_BREAKDOWN_RESPONSE_EXAMPLE = {
    "lookback_minutes": 1440,
    "total_backlog_jobs": 8,
    "largest_group_backlog_jobs": 6,
    "largest_group_backlog_share": "0.75",
    "top_3_backlog_share": "1.0",
    "groups": [
        {
            "endpoint": "/ingest/transactions",
            "entity_type": "transaction",
            "total_jobs": 10,
            "accepted_jobs": 2,
            "queued_jobs": 4,
            "failed_jobs": 4,
            "backlog_jobs": 6,
            "oldest_backlog_submitted_at": "2026-03-03T04:10:11.000Z",
            "oldest_backlog_age_seconds": 127.5,
            "failure_rate": "0.4",
        },
        {
            "endpoint": "/ingest/instruments",
            "entity_type": "instrument",
            "total_jobs": 4,
            "accepted_jobs": 1,
            "queued_jobs": 1,
            "failed_jobs": 2,
            "backlog_jobs": 2,
            "oldest_backlog_submitted_at": "2026-03-03T04:11:03.000Z",
            "oldest_backlog_age_seconds": 75.0,
            "failure_rate": "0.5",
        },
    ],
}

INGESTION_STALLED_JOB_LIST_RESPONSE_EXAMPLE = {
    "threshold_seconds": 300,
    "total": 2,
    "jobs": [
        {
            "job_id": "job_stalled_001",
            "endpoint": "/ingest/transactions",
            "entity_type": "transaction",
            "status": "accepted",
            "submitted_at": "2026-03-03T04:10:11.000Z",
            "queue_age_seconds": 901.0,
            "retry_count": 0,
            "suggested_action": (
                "Investigate consumer lag and retry this job once root cause is resolved."
            ),
        },
        {
            "job_id": "job_stalled_002",
            "endpoint": "/ingest/portfolio-bundles",
            "entity_type": "portfolio_bundle",
            "status": "queued",
            "submitted_at": "2026-03-03T03:58:02.000Z",
            "queue_age_seconds": 1632.5,
            "retry_count": 2,
            "suggested_action": (
                "Inspect downstream dependency saturation before forcing replay or pausing intake."
            ),
        },
    ],
}

CONSUMER_DLQ_EVENT_LIST_RESPONSE_EXAMPLE = {
    "events": [
        {
            "event_id": "cdlq_01J5VK4Y4EPMTVF1B0HF4CAHB6",
            "original_topic": "transactions.raw.received",
            "consumer_group": "persistence-service-group",
            "dlq_topic": "dlq.persistence_service",
            "original_key": "TXN-2026-000145",
            "error_reason_code": "VALIDATION_ERROR",
            "error_reason": "ValidationError: portfolio_id is required",
            "correlation_id": "ING:7f4a64b0-35f4-41bc-8f74-cb556f2ad9a3",
            "payload_excerpt": '{"transaction_id":"TXN-2026-000145"}',
            "observed_at": "2026-03-06T09:11:05.812Z",
        },
        {
            "event_id": "cdlq_01J5VK612V7N8J1RP4PD7NCQ44",
            "original_topic": "portfolio-bundles.raw.received",
            "consumer_group": "valuation-service-group",
            "dlq_topic": "dlq.valuation_service",
            "original_key": "BUNDLE-2026-000014",
            "error_reason_code": "DEPENDENCY_TIMEOUT",
            "error_reason": "TimeoutError: valuation dependency exceeded 5s SLA",
            "correlation_id": "ING:e59dd219-3902-4f38-8f8d-7c6cb1456672",
            "payload_excerpt": '{"bundle_id":"BUNDLE-2026-000014"}',
            "observed_at": "2026-03-06T09:15:42.114Z",
        },
    ],
    "total": 2,
}

INGESTION_RETRY_REQUEST_EXAMPLES = {
    "full_retry": {
        "summary": "Replay the full stored payload",
        "value": {"record_keys": [], "dry_run": False},
    },
    "partial_dry_run": {
        "summary": "Validate a partial replay without publishing",
        "value": {"record_keys": ["TXN-2026-000145", "TXN-2026-000146"], "dry_run": True},
    },
}

CONSUMER_DLQ_REPLAY_REQUEST_EXAMPLES = {
    "replay_now": {
        "summary": "Replay correlated payload now",
        "value": {"dry_run": False},
    },
    "dry_run": {
        "summary": "Validate replayability only",
        "value": {"dry_run": True},
    },
}

CONSUMER_DLQ_REPLAY_RESPONSE_EXAMPLE = {
    "event_id": "cdlq_01J5VK4Y4EPMTVF1B0HF4CAHB6",
    "correlation_id": "ING:7f4a64b0-35f4-41bc-8f74-cb556f2ad9a3",
    "job_id": "job_01J5S0J6D3BAVMK2E1V0WQ7MCC",
    "replay_status": "replayed",
    "replay_audit_id": "replay_01J5WK1G7S3HBQ7Q3M0E3TMT0P",
    "replay_fingerprint": "c5b0faeb7de60bc111f109624e58d0ad6206634be5fef4d4455cdac629df4f3f",
    "message": "Replayed ingestion job from correlated consumer DLQ event.",
}

INGESTION_REPLAY_AUDIT_RESPONSE_EXAMPLE = {
    "replay_id": "replay_01J5WK1G7S3HBQ7Q3M0E3TMT0P",
    "recovery_path": "consumer_dlq_replay",
    "event_id": "cdlq_01J5VK4Y4EPMTVF1B0HF4CAHB6",
    "replay_fingerprint": "c5b0faeb7de60bc111f109624e58d0ad6206634be5fef4d4455cdac629df4f3f",
    "correlation_id": "ING:7f4a64b0-35f4-41bc-8f74-cb556f2ad9a3",
    "job_id": "job_01J5S0J6D3BAVMK2E1V0WQ7MCC",
    "endpoint": "/ingest/transactions",
    "replay_status": "replayed",
    "dry_run": False,
    "replay_reason": "Replayed ingestion job from correlated consumer DLQ event.",
    "requested_by": "ops-token",
    "requested_at": "2026-03-06T10:12:01.019Z",
    "completed_at": "2026-03-06T10:12:02.039Z",
}

INGESTION_REPLAY_AUDIT_LIST_RESPONSE_EXAMPLE = {
    "audits": [
        INGESTION_REPLAY_AUDIT_RESPONSE_EXAMPLE,
        {
            "replay_id": "replay_01J5WK2V8GE7K9VK2R6TFY4KQZ",
            "recovery_path": "consumer_dlq_replay",
            "event_id": "cdlq_01J5VK612V7N8J1RP4PD7NCQ44",
            "replay_fingerprint": (
                "8d9d2ddf66ef6a5c5f0fbd7654a7de0b7f7982393e0d3b599d4fa32e84793d09"
            ),
            "correlation_id": "ING:e59dd219-3902-4f38-8f8d-7c6cb1456672",
            "job_id": "job_01J5S0M3BVX8M5A4SK13Q20D8D",
            "endpoint": "/ingest/portfolio-bundles",
            "replay_status": "dry_run",
            "dry_run": True,
            "replay_reason": "Dry-run successful. Correlated ingestion job is replayable.",
            "requested_by": "ops-token",
            "requested_at": "2026-03-06T10:20:11.019Z",
            "completed_at": "2026-03-06T10:20:11.442Z",
        },
    ],
    "total": 2,
}

INGESTION_OPS_MODE_EXAMPLE = {
    "mode": "paused",
    "replay_window_start": "2026-03-06T00:00:00Z",
    "replay_window_end": "2026-03-06T06:00:00Z",
    "updated_by": "ops_automation",
    "updated_at": "2026-03-06T02:15:07.234Z",
}

INGESTION_IDEMPOTENCY_DIAGNOSTICS_RESPONSE_EXAMPLE = {
    "lookback_minutes": 1440,
    "total_keys": 2,
    "collisions": 1,
    "keys": [
        {
            "idempotency_key": "integration-ingestion-idempotency-001",
            "usage_count": 3,
            "endpoint_count": 2,
            "endpoints": ["/ingest/transactions", "/ingest/portfolio-bundles"],
            "first_seen_at": "2026-03-06T07:10:11.211Z",
            "last_seen_at": "2026-03-06T07:15:01.127Z",
            "collision_detected": True,
        },
        {
            "idempotency_key": "integration-ingestion-idempotency-002",
            "usage_count": 2,
            "endpoint_count": 1,
            "endpoints": ["/ingest/transactions"],
            "first_seen_at": "2026-03-06T08:01:03.000Z",
            "last_seen_at": "2026-03-06T08:05:17.000Z",
            "collision_detected": False,
        },
    ],
}

INGESTION_JOB_NOT_FOUND_EXAMPLE = {
    "detail": {
        "code": "INGESTION_JOB_NOT_FOUND",
        "message": "Ingestion job 'job_01J5S0J6D3BAVMK2E1V0WQ7MCC' was not found.",
    }
}

INGESTION_JOB_RETRY_UNSUPPORTED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_JOB_RETRY_UNSUPPORTED",
        "message": (
            "Ingestion job 'job_01J5S0J6D3BAVMK2E1V0WQ7MCC' does not have stored request "
            "payload and cannot be retried."
        ),
    }
}

INGESTION_JOB_PARTIAL_RETRY_UNSUPPORTED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_PARTIAL_RETRY_UNSUPPORTED",
        "message": "Partial retry is not supported for endpoint '/ingest/market-prices'.",
    }
}

INGESTION_JOB_RETRY_BLOCKED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_RETRY_BLOCKED",
        "message": "Retries are blocked while ingestion is paused.",
    }
}

INGESTION_JOB_RETRY_DUPLICATE_BLOCKED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_RETRY_DUPLICATE_BLOCKED",
        "message": "Retry blocked because an equivalent deterministic replay already succeeded.",
        "replay_fingerprint": "c5b0faeb7de60bc111f109624e58d0ad6206634be5fef4d4455cdac629df4f3f",
    }
}

INGESTION_JOB_RETRY_BOOKKEEPING_FAILED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_RETRY_BOOKKEEPING_FAILED",
        "message": (
            "Replay publish succeeded but post-publish bookkeeping failed: queue state write failed"
        ),
        "replay_audit_id": "replay_01J5WK1G7S3HBQ7Q3M0E3TMT0P",
        "replay_fingerprint": "c5b0faeb7de60bc111f109624e58d0ad6206634be5fef4d4455cdac629df4f3f",
    }
}

INGESTION_CONSUMER_DLQ_EVENT_NOT_FOUND_EXAMPLE = {
    "detail": {
        "code": "INGESTION_CONSUMER_DLQ_EVENT_NOT_FOUND",
        "message": ("Consumer DLQ event 'cdlq_01J5VK4Y4EPMTVF1B0HF4CAHB6' was not found."),
    }
}

INGESTION_REPLAY_AUDIT_NOT_FOUND_EXAMPLE = {
    "detail": {
        "code": "INGESTION_REPLAY_AUDIT_NOT_FOUND",
        "message": "Replay audit 'replay_01J5WK1G7S3HBQ7Q3M0E3TMT0P' was not found.",
    }
}


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


async def _record_replay_audit_best_effort(
    *,
    ingestion_job_service: IngestionJobService,
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
) -> str | None:
    try:
        return await ingestion_job_service.record_consumer_dlq_replay_audit(
            recovery_path=recovery_path,
            event_id=event_id,
            replay_fingerprint=replay_fingerprint,
            correlation_id=correlation_id,
            job_id=job_id,
            endpoint=endpoint,
            replay_status=replay_status,
            dry_run=dry_run,
            replay_reason=replay_reason,
            requested_by=requested_by,
        )
    except Exception:
        logger.exception(
            "Failed to record replay audit row.",
            extra={
                "recovery_path": recovery_path,
                "event_id": event_id,
                "job_id": job_id,
                "replay_status": replay_status,
            },
        )
        return None


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
        await ingestion_service.publish_reprocessing_requests(
            request_model.transaction_ids,
            idempotency_key=idempotency_key,
        )
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
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    jobs, next_cursor = await ingestion_job_service.list_jobs(
        status=status,
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
            "description": "Replay publish succeeded but retry bookkeeping failed.",
            "content": {
                "application/json": {"example": INGESTION_JOB_RETRY_BOOKKEEPING_FAILED_EXAMPLE}
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
                    "Retry blocked because an equivalent deterministic replay already succeeded."
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

    try:
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
        replay_reason = f"Replay publish succeeded but post-publish bookkeeping failed: {exc}"
        replay_audit_id = await _record_replay_audit_best_effort(
            ingestion_job_service=ingestion_job_service,
            recovery_path="ingestion_job_retry",
            event_id=f"job:{job_id}",
            replay_fingerprint=replay_fingerprint,
            correlation_id=None,
            job_id=job_id,
            endpoint=context.endpoint,
            replay_status="replayed_bookkeeping_failed",
            dry_run=False,
            replay_reason=replay_reason,
            requested_by=ops_actor,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INGESTION_RETRY_BOOKKEEPING_FAILED",
                "message": replay_reason,
                "replay_audit_id": replay_audit_id,
                "replay_fingerprint": replay_fingerprint,
            },
        ) from exc

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
                "DLQ event has no correlation id and cannot be mapped to ingestion payload."
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

    try:
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
        replay_reason = f"Replay publish succeeded but post-publish bookkeeping failed: {exc}"
        replay_audit_id = await _record_replay_audit_best_effort(
            ingestion_job_service=ingestion_job_service,
            recovery_path="consumer_dlq_replay",
            event_id=event_id,
            replay_fingerprint=replay_fingerprint,
            correlation_id=event.correlation_id,
            job_id=replay_job_id,
            endpoint=context.endpoint,
            replay_status="replayed_bookkeeping_failed",
            dry_run=False,
            replay_reason=replay_reason,
            requested_by=ops_actor,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INGESTION_DLQ_REPLAY_BOOKKEEPING_FAILED",
                "message": replay_reason,
                "replay_audit_id": replay_audit_id,
                "replay_fingerprint": replay_fingerprint,
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
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    if (
        update_request.replay_window_start
        and update_request.replay_window_end
        and update_request.replay_window_start > update_request.replay_window_end
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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
