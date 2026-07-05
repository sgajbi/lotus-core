from __future__ import annotations

from typing import Any

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
            "correlation_missing_reason": None,
            "alternate_lookup_key": None,
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
            "correlation_missing_reason": None,
            "alternate_lookup_key": None,
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
    "correlation_missing_reason": None,
    "alternate_lookup_key": None,
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
    "correlation_missing_reason": None,
    "alternate_lookup_key": None,
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
            "correlation_missing_reason": None,
            "alternate_lookup_key": None,
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
            "payload_fingerprint_count": 2,
            "max_payload_fingerprints_per_endpoint": 1,
            "endpoints": ["/ingest/transactions", "/ingest/portfolio-bundles"],
            "first_seen_at": "2026-03-06T07:10:11.211Z",
            "last_seen_at": "2026-03-06T07:15:01.127Z",
            "collision_detected": True,
            "payload_conflict_detected": False,
            "reuse_classification": "cross_endpoint_reuse",
        },
        {
            "idempotency_key": "integration-ingestion-idempotency-002",
            "usage_count": 2,
            "endpoint_count": 1,
            "payload_fingerprint_count": 1,
            "max_payload_fingerprints_per_endpoint": 1,
            "endpoints": ["/ingest/transactions"],
            "first_seen_at": "2026-03-06T08:01:03.000Z",
            "last_seen_at": "2026-03-06T08:05:17.000Z",
            "collision_detected": False,
            "payload_conflict_detected": False,
            "reuse_classification": "single_record_or_benign_replay",
        },
    ],
}

INGESTION_JOB_NOT_FOUND_EXAMPLE = {
    "detail": {
        "code": "INGESTION_JOB_NOT_FOUND",
        "message": "Ingestion job 'job_01J5S0J6D3BAVMK2E1V0WQ7MCC' was not found.",
        "outcome": "not_found",
        "remediation": "Verify the ingestion job id from the operations job list before retrying.",
        "recovery_path": "ingestion_job_retry",
    }
}

INGESTION_JOB_RETRY_UNSUPPORTED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_JOB_RETRY_UNSUPPORTED",
        "message": (
            "Ingestion job 'job_01J5S0J6D3BAVMK2E1V0WQ7MCC' does not have stored request "
            "payload and cannot be retried."
        ),
        "outcome": "retry_unsupported",
        "remediation": (
            "Recover the source batch from upstream records; this job has no durable replay "
            "payload."
        ),
        "recovery_path": "ingestion_job_retry",
    }
}

INGESTION_JOB_PARTIAL_RETRY_UNSUPPORTED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_PARTIAL_RETRY_UNSUPPORTED",
        "message": "Partial retry is not supported for endpoint '/ingest/market-prices'.",
        "outcome": "partial_retry_unsupported",
        "remediation": (
            "Retry the full stored payload or use an endpoint with governed partial retry support."
        ),
        "recovery_path": "ingestion_job_retry",
    }
}

INGESTION_JOB_RETRY_BLOCKED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_RETRY_BLOCKED",
        "message": "Retries are blocked while ingestion is paused.",
        "outcome": "retry_blocked",
        "remediation": (
            "Resume ingestion operations mode or wait for the replay window to permit retries."
        ),
        "recovery_path": "ingestion_job_retry",
    }
}

INGESTION_JOB_RETRY_DUPLICATE_BLOCKED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_RETRY_DUPLICATE_BLOCKED",
        "message": "Retry blocked because an equivalent deterministic replay already succeeded.",
        "outcome": "duplicate_blocked",
        "remediation": (
            "Inspect the existing replay audit before forcing any manual recovery action."
        ),
        "recovery_path": "ingestion_job_retry",
        "replay_fingerprint": "c5b0faeb7de60bc111f109624e58d0ad6206634be5fef4d4455cdac629df4f3f",
    }
}

INGESTION_JOB_RETRY_PUBLISH_FAILED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_RETRY_PUBLISH_FAILED",
        "message": (
            "Ingestion job retry could not be published to the downstream ingestion pipeline."
        ),
        "outcome": "publish_failed",
        "remediation": (
            "Check ingestion publisher health and retry after the downstream publish path recovers."
        ),
        "recovery_path": "ingestion_job_retry",
        "replay_audit_id": "replay_01J5WK1G7S3HBQ7Q3M0E3TMT0P",
        "replay_fingerprint": "c5b0faeb7de60bc111f109624e58d0ad6206634be5fef4d4455cdac629df4f3f",
    }
}

INGESTION_JOB_RETRY_BOOKKEEPING_FAILED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_RETRY_BOOKKEEPING_FAILED",
        "message": ("Replay publish succeeded but post-publish bookkeeping did not complete."),
        "outcome": "bookkeeping_failed",
        "remediation": (
            "Inspect replay audit state and job queue state before retrying or reconciling "
            "manually."
        ),
        "recovery_path": "ingestion_job_retry",
        "replay_audit_id": "replay_01J5WK1G7S3HBQ7Q3M0E3TMT0P",
        "replay_fingerprint": "c5b0faeb7de60bc111f109624e58d0ad6206634be5fef4d4455cdac629df4f3f",
    }
}

INGESTION_REPLAY_AUDIT_WRITE_FAILED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_REPLAY_AUDIT_WRITE_FAILED",
        "message": "Replay audit could not be recorded; replay outcome was not acknowledged.",
        "outcome": "audit_write_failed",
        "remediation": (
            "Do not assume replay completion; restore replay audit persistence and retry safely."
        ),
        "recovery_path": "ingestion_job_retry",
        "event_id": "job:job_01J5S0J6D3BAVMK2E1V0WQ7MCC",
        "job_id": "job_01J5S0J6D3BAVMK2E1V0WQ7MCC",
        "replay_status": "replayed_bookkeeping_failed",
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

INGESTION_BOOKKEEPING_REPAIR_RESPONSE_EXAMPLE = {
    "job_id": "job_01J5S0J6D3BAVMK2E1V0WQ7MCC",
    "previous_status": "accepted",
    "repaired_status": "queued",
    "recovery_action": "repair_ingestion_job_bookkeeping",
    "supportability_reason_code": "POST_PUBLISH_BOOKKEEPING_FAILED",
    "retry_safe": False,
    "message": "Ingestion job bookkeeping repaired from accepted to queued.",
}

INGESTION_BOOKKEEPING_REPAIR_NOT_ELIGIBLE_EXAMPLE = {
    "detail": {
        "code": "INGESTION_BOOKKEEPING_REPAIR_NOT_ELIGIBLE",
        "message": "Ingestion job is not eligible for bookkeeping repair.",
        "job_id": "job_01J5S0J6D3BAVMK2E1V0WQ7MCC",
        "status": "failed",
    }
}

INGESTION_BOOKKEEPING_REPAIR_FAILED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_BOOKKEEPING_REPAIR_FAILED",
        "message": "Ingestion job bookkeeping repair did not complete.",
        "job_id": "job_01J5S0J6D3BAVMK2E1V0WQ7MCC",
        "recovery_action": "repair_ingestion_job_bookkeeping",
    }
}


INGESTION_OPERATION_EXAMPLE_NAMES = (
    "INGESTION_JOB_RESPONSE_EXAMPLE",
    "INGESTION_JOB_FAILURE_LIST_RESPONSE_EXAMPLE",
    "INGESTION_JOB_RECORD_STATUS_RESPONSE_EXAMPLE",
    "INGESTION_HEALTH_SUMMARY_RESPONSE_EXAMPLE",
    "INGESTION_CONSUMER_LAG_RESPONSE_EXAMPLE",
    "INGESTION_SLO_STATUS_RESPONSE_EXAMPLE",
    "INGESTION_ERROR_BUDGET_STATUS_RESPONSE_EXAMPLE",
    "INGESTION_OPERATING_BAND_RESPONSE_EXAMPLE",
    "INGESTION_OPS_POLICY_RESPONSE_EXAMPLE",
    "INGESTION_REPROCESSING_QUEUE_HEALTH_RESPONSE_EXAMPLE",
    "INGESTION_CAPACITY_STATUS_RESPONSE_EXAMPLE",
    "INGESTION_BACKLOG_BREAKDOWN_RESPONSE_EXAMPLE",
    "INGESTION_STALLED_JOB_LIST_RESPONSE_EXAMPLE",
    "CONSUMER_DLQ_EVENT_LIST_RESPONSE_EXAMPLE",
    "INGESTION_RETRY_REQUEST_EXAMPLES",
    "CONSUMER_DLQ_REPLAY_REQUEST_EXAMPLES",
    "CONSUMER_DLQ_REPLAY_RESPONSE_EXAMPLE",
    "INGESTION_REPLAY_AUDIT_RESPONSE_EXAMPLE",
    "INGESTION_REPLAY_AUDIT_LIST_RESPONSE_EXAMPLE",
    "INGESTION_OPS_MODE_EXAMPLE",
    "INGESTION_IDEMPOTENCY_DIAGNOSTICS_RESPONSE_EXAMPLE",
    "INGESTION_JOB_NOT_FOUND_EXAMPLE",
    "INGESTION_JOB_RETRY_UNSUPPORTED_EXAMPLE",
    "INGESTION_JOB_PARTIAL_RETRY_UNSUPPORTED_EXAMPLE",
    "INGESTION_JOB_RETRY_BLOCKED_EXAMPLE",
    "INGESTION_JOB_RETRY_DUPLICATE_BLOCKED_EXAMPLE",
    "INGESTION_JOB_RETRY_PUBLISH_FAILED_EXAMPLE",
    "INGESTION_JOB_RETRY_BOOKKEEPING_FAILED_EXAMPLE",
    "INGESTION_REPLAY_AUDIT_WRITE_FAILED_EXAMPLE",
    "INGESTION_CONSUMER_DLQ_EVENT_NOT_FOUND_EXAMPLE",
    "INGESTION_REPLAY_AUDIT_NOT_FOUND_EXAMPLE",
    "INGESTION_BOOKKEEPING_REPAIR_RESPONSE_EXAMPLE",
    "INGESTION_BOOKKEEPING_REPAIR_NOT_ELIGIBLE_EXAMPLE",
    "INGESTION_BOOKKEEPING_REPAIR_FAILED_EXAMPLE",
)

INGESTION_OPERATION_EXAMPLES: dict[str, Any] = {
    name: globals()[name] for name in INGESTION_OPERATION_EXAMPLE_NAMES
}
