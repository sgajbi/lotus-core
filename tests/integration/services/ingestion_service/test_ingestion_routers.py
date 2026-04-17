# tests/integration/services/ingestion-service/test_ingestion_routers.py
import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
import pytest_asyncio
from openpyxl import Workbook
from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer

from src.services.event_replay_service.app.main import app as event_replay_app
from src.services.ingestion_service.app import ops_controls
from src.services.ingestion_service.app.DTOs.ingestion_job_dto import IngestionJobResponse
from src.services.ingestion_service.app.main import app

try:
    from app import ops_controls as app_ops_controls
except ModuleNotFoundError:  # pragma: no cover - only needed in certain test path setups.
    app_ops_controls = ops_controls
from src.services.event_replay_service.app.routers import (
    ingestion_operations as ingestion_operations_router,
)
from src.services.ingestion_service.app.routers import (
    business_dates as business_dates_router,
)
from src.services.ingestion_service.app.routers import (
    fx_rates as fx_rates_router,
)
from src.services.ingestion_service.app.routers import (
    instruments as instruments_router,
)
from src.services.ingestion_service.app.routers import (
    market_prices as market_prices_router,
)
from src.services.ingestion_service.app.routers import (
    portfolio_bundle as portfolio_bundle_router,
)
from src.services.ingestion_service.app.routers import (
    portfolios as portfolios_router,
)
from src.services.ingestion_service.app.routers import (
    reference_data as reference_data_router,
)
from src.services.ingestion_service.app.routers import (
    reprocessing as reprocessing_router,
)
from src.services.ingestion_service.app.routers import (
    transactions as transactions_router,
)
from src.services.ingestion_service.app.services.ingestion_job_service import (
    get_ingestion_job_service,
)

# Mark all tests in this file as async
pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_kafka_producer() -> MagicMock:
    """Provides a mock KafkaProducer."""
    mock = MagicMock(spec=KafkaProducer)
    mock.publish_message = MagicMock()
    mock.flush.return_value = 0
    return mock


@pytest_asyncio.fixture
async def ingestion_test_harness(mock_kafka_producer: MagicMock):
    """
    Provides an httpx.AsyncClient with the KafkaProducer dependency replaced by a MagicMock.
    """

    def override_get_kafka_producer():
        return mock_kafka_producer

    class FakeIngestionJobService:
        def __init__(self):
            self.jobs: dict[str, IngestionJobResponse] = {}
            self.job_payloads: dict[str, dict] = {}
            self.failures: dict[str, list[dict]] = {}
            self.replay_audit: dict[str, dict] = {}
            self.fail_mark_queued_job_ids: set[str] = set()
            self.fail_mark_retried_job_ids: set[str] = set()
            self.fail_next_mark_queued = False
            self.mode = "normal"
            self.reprocessing_publish_allowed = True
            self.replay_window_start = None
            self.replay_window_end = None

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
            request_payload: dict | None,
        ) -> SimpleNamespace:
            if idempotency_key:
                for existing in self.jobs.values():
                    if (
                        existing.endpoint == endpoint
                        and existing.idempotency_key == idempotency_key
                    ):
                        return SimpleNamespace(job=existing, created=False)
            self.jobs[job_id] = IngestionJobResponse(
                job_id=job_id,
                endpoint=endpoint,
                entity_type=entity_type,
                status="accepted",
                accepted_count=accepted_count,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
                request_id=request_id,
                trace_id=trace_id,
                submitted_at=datetime.now(UTC),
                completed_at=None,
                failure_reason=None,
                retry_count=0,
                last_retried_at=None,
            )
            if request_payload:
                self.job_payloads[job_id] = request_payload
            return SimpleNamespace(job=self.jobs[job_id], created=True)

        async def mark_queued(self, job_id: str) -> None:
            if self.fail_next_mark_queued:
                self.fail_next_mark_queued = False
                raise RuntimeError("queue state write failed")
            if job_id in self.fail_mark_queued_job_ids:
                raise RuntimeError("queue state write failed")
            if job_id not in self.jobs:
                return
            record = self.jobs[job_id]
            record.status = "queued"
            record.completed_at = datetime.now(UTC)
            self.jobs[job_id] = record

        async def mark_failed(
            self,
            job_id: str,
            failure_reason: str,
            failure_phase: str = "publish",
            failed_record_keys: list[str] | None = None,
        ) -> None:
            if job_id not in self.jobs:
                return
            record = self.jobs[job_id]
            record.status = "failed"
            record.failure_reason = failure_reason
            record.completed_at = datetime.now(UTC)
            self.jobs[job_id] = record
            self.failures.setdefault(job_id, []).append(
                {
                    "failure_id": f"fail_{len(self.failures.get(job_id, [])) + 1}",
                    "job_id": job_id,
                    "failure_phase": failure_phase,
                    "failure_reason": failure_reason,
                    "failed_record_keys": failed_record_keys or [],
                    "failed_at": datetime.now(UTC),
                }
            )

        async def record_failure_observation(
            self,
            job_id: str,
            failure_reason: str,
            *,
            failure_phase: str,
            failed_record_keys: list[str] | None = None,
        ) -> None:
            self.failures.setdefault(job_id, []).append(
                {
                    "failure_id": f"fail_{len(self.failures.get(job_id, [])) + 1}",
                    "job_id": job_id,
                    "failure_phase": failure_phase,
                    "failure_reason": failure_reason,
                    "failed_record_keys": failed_record_keys or [],
                    "failed_at": datetime.now(UTC),
                }
            )

        async def mark_retried(self, job_id: str) -> None:
            if job_id in self.fail_mark_retried_job_ids:
                raise RuntimeError("retry accounting write failed")
            if job_id not in self.jobs:
                return
            record = self.jobs[job_id]
            record.retry_count += 1
            record.last_retried_at = datetime.now(UTC)
            self.jobs[job_id] = record

        async def get_job(self, job_id: str) -> IngestionJobResponse | None:
            return self.jobs.get(job_id)

        async def get_job_replay_context(self, job_id: str) -> SimpleNamespace | None:
            record = self.jobs.get(job_id)
            if record is None:
                return None
            return SimpleNamespace(
                job_id=job_id,
                endpoint=record.endpoint,
                entity_type=record.entity_type,
                accepted_count=record.accepted_count,
                idempotency_key=record.idempotency_key,
                request_payload=self.job_payloads.get(job_id),
                submitted_at=record.submitted_at,
            )

        async def list_jobs(
            self,
            *,
            status: str | None = None,
            entity_type: str | None = None,
            submitted_from: datetime | None = None,
            submitted_to: datetime | None = None,
            cursor: str | None = None,
            limit: int = 100,
        ) -> tuple[list[IngestionJobResponse], str | None]:
            values = list(self.jobs.values())
            filtered = [
                job
                for job in values
                if (status is None or job.status == status)
                and (entity_type is None or job.entity_type == entity_type)
                and (submitted_from is None or job.submitted_at >= submitted_from)
                and (submitted_to is None or job.submitted_at <= submitted_to)
            ]
            if cursor:
                for idx, row in enumerate(filtered):
                    if row.job_id == cursor:
                        filtered = filtered[idx + 1 :]
                        break
            return ([job.model_dump(mode="json") for job in filtered[:limit]], None)

        async def list_failures(self, job_id: str, limit: int = 100) -> list[dict]:
            return self.failures.get(job_id, [])[:limit]

        async def get_health_summary(self):
            total_jobs = len(self.jobs)
            accepted_jobs = sum(1 for j in self.jobs.values() if j.status == "accepted")
            queued_jobs = sum(1 for j in self.jobs.values() if j.status == "queued")
            failed_jobs = sum(1 for j in self.jobs.values() if j.status == "failed")
            return {
                "total_jobs": total_jobs,
                "accepted_jobs": accepted_jobs,
                "queued_jobs": queued_jobs,
                "failed_jobs": failed_jobs,
                "backlog_jobs": accepted_jobs + queued_jobs,
            }

        async def get_slo_status(
            self,
            *,
            lookback_minutes: int = 60,
            failure_rate_threshold: Decimal = Decimal("0.03"),
            queue_latency_threshold_seconds: float = 5.0,
            backlog_age_threshold_seconds: float = 300.0,
        ):
            total_jobs = len(self.jobs)
            failed_jobs = sum(1 for j in self.jobs.values() if j.status == "failed")
            failure_rate = (
                Decimal(failed_jobs) / Decimal(total_jobs) if total_jobs else Decimal("0")
            )
            return {
                "lookback_minutes": lookback_minutes,
                "total_jobs": total_jobs,
                "failed_jobs": failed_jobs,
                "failure_rate": failure_rate,
                "p95_queue_latency_seconds": 0.2,
                "backlog_age_seconds": 0.0,
                "breach_failure_rate": failure_rate > failure_rate_threshold,
                "breach_queue_latency": False,
                "breach_backlog_age": False,
            }

        async def get_backlog_breakdown(
            self,
            *,
            lookback_minutes: int = 1440,
            limit: int = 200,
        ):
            return {
                "lookback_minutes": lookback_minutes,
                "total_backlog_jobs": 1,
                "largest_group_backlog_jobs": 1,
                "largest_group_backlog_share": Decimal("1"),
                "top_3_backlog_share": Decimal("1"),
                "groups": [
                    {
                        "endpoint": "/ingest/transactions",
                        "entity_type": "transaction",
                        "total_jobs": 3,
                        "accepted_jobs": 1,
                        "queued_jobs": 0,
                        "failed_jobs": 2,
                        "backlog_jobs": 1,
                        "oldest_backlog_submitted_at": datetime.now(UTC),
                        "oldest_backlog_age_seconds": 12.0,
                        "failure_rate": Decimal("0.6667"),
                    }
                ][:limit],
            }

        async def list_stalled_jobs(
            self,
            *,
            threshold_seconds: int = 300,
            limit: int = 100,
        ):
            return {
                "threshold_seconds": threshold_seconds,
                "total": 1,
                "jobs": [
                    {
                        "job_id": "job_stalled_001",
                        "endpoint": "/ingest/transactions",
                        "entity_type": "transaction",
                        "status": "accepted",
                        "submitted_at": datetime.now(UTC),
                        "queue_age_seconds": 901.0,
                        "retry_count": 0,
                        "suggested_action": (
                            "Investigate consumer lag and retry this job once root cause is resolved."  # noqa: E501
                        ),
                    }
                ][:limit],
            }

        async def list_consumer_dlq_events(
            self,
            *,
            limit: int = 100,
            original_topic: str | None = None,
            consumer_group: str | None = None,
        ) -> list[dict]:
            return [
                {
                    "event_id": "cdlq_test_001",
                    "original_topic": original_topic or "transactions.raw.received",
                    "consumer_group": consumer_group or "persistence-service-group",
                    "dlq_topic": "dlq.persistence_service",
                    "original_key": "TXN-2026-000145",
                    "error_reason_code": "VALIDATION_ERROR",
                    "error_reason": "ValidationError: portfolio_id is required",
                    "correlation_id": "ING:test-correlation-id",
                    "payload_excerpt": '{"transaction_id":"TXN-2026-000145"}',
                    "observed_at": datetime.now(UTC),
                }
            ][:limit]

        async def get_consumer_dlq_event(self, event_id: str):
            if event_id != "cdlq_test_001":
                return None
            return SimpleNamespace(
                event_id=event_id,
                original_topic="transactions.raw.received",
                consumer_group="persistence-service-group",
                dlq_topic="dlq.persistence_service",
                original_key="TXN-2026-000145",
                error_reason_code="VALIDATION_ERROR",
                error_reason="ValidationError: portfolio_id is required",
                correlation_id="ING:test-correlation-id",
                payload_excerpt='{"transaction_id":"TXN-2026-000145"}',
                observed_at=datetime.now(UTC),
            )

        async def get_consumer_lag(
            self,
            *,
            lookback_minutes: int = 60,
            limit: int = 100,
        ):
            return {
                "lookback_minutes": lookback_minutes,
                "backlog_jobs": 1,
                "total_groups": 1,
                "groups": [
                    {
                        "consumer_group": "persistence-service-group",
                        "original_topic": "transactions.raw.received",
                        "dlq_events": 3,
                        "last_observed_at": datetime.now(UTC),
                        "lag_severity": "low",
                    }
                ][:limit],
            }

        async def get_job_record_status(self, job_id: str):
            job = self.jobs.get(job_id)
            if not job:
                return None
            return {
                "job_id": job_id,
                "entity_type": job.entity_type,
                "accepted_count": job.accepted_count,
                "failed_record_keys": ["TXN-2026-000145"],
                "replayable_record_keys": ["TXN-2026-000145", "TXN-2026-000146"],
            }

        async def get_idempotency_diagnostics(
            self,
            *,
            lookback_minutes: int = 1440,
            limit: int = 200,
        ):
            return {
                "lookback_minutes": lookback_minutes,
                "total_keys": 1,
                "collisions": 0,
                "keys": [
                    {
                        "idempotency_key": "integration-ingestion-idempotency-001",
                        "usage_count": 2,
                        "endpoint_count": 1,
                        "endpoints": ["/ingest/transactions"],
                        "first_seen_at": datetime.now(UTC),
                        "last_seen_at": datetime.now(UTC),
                        "collision_detected": False,
                    }
                ][:limit],
            }

        async def get_error_budget_status(
            self,
            *,
            lookback_minutes: int = 60,
            failure_rate_threshold: Decimal = Decimal("0.03"),
            backlog_growth_threshold: int = 5,
        ):
            return {
                "lookback_minutes": lookback_minutes,
                "previous_lookback_minutes": lookback_minutes,
                "total_jobs": len(self.jobs),
                "failed_jobs": 0,
                "failure_rate": Decimal("0"),
                "remaining_error_budget": failure_rate_threshold,
                "backlog_jobs": 1,
                "previous_backlog_jobs": 1,
                "backlog_growth": 0,
                "replay_backlog_pressure_ratio": Decimal("0.0002"),
                "dlq_events_in_window": 0,
                "dlq_budget_events_per_window": 10,
                "dlq_pressure_ratio": Decimal("0"),
                "breach_failure_rate": False,
                "breach_backlog_growth": False,
            }

        async def get_operating_band(
            self,
            *,
            lookback_minutes: int = 60,
            failure_rate_threshold: Decimal = Decimal("0.03"),
            queue_latency_threshold_seconds: float = 5.0,
            backlog_age_threshold_seconds: float = 300.0,
        ):
            return {
                "lookback_minutes": lookback_minutes,
                "operating_band": "yellow",
                "recommended_action": "Scale up one band and monitor DLQ pressure.",
                "backlog_age_seconds": 42.0,
                "dlq_pressure_ratio": Decimal("0.25"),
                "failure_rate": Decimal("0"),
                "triggered_signals": ["backlog_age_seconds>=15", "dlq_pressure_ratio>=0.25"],
            }

        async def get_operating_policy(self):
            return {
                "policy_version": "v1",
                "policy_fingerprint": "e6a9f2cc3bb5e5a7",
                "lookback_minutes_default": 60,
                "failure_rate_threshold_default": Decimal("0.03"),
                "queue_latency_threshold_seconds_default": 5.0,
                "backlog_age_threshold_seconds_default": 300.0,
                "replay_max_records_per_request": 5000,
                "replay_max_backlog_jobs": 5000,
                "reprocessing_worker_poll_interval_seconds": 10,
                "reprocessing_worker_batch_size": 10,
                "valuation_scheduler_poll_interval_seconds": 30,
                "valuation_scheduler_batch_size": 100,
                "valuation_scheduler_dispatch_rounds": 3,
                "dlq_budget_events_per_window": 10,
                "operating_band_yellow_backlog_age_seconds": 15.0,
                "operating_band_orange_backlog_age_seconds": 60.0,
                "operating_band_red_backlog_age_seconds": 180.0,
                "operating_band_yellow_dlq_pressure_ratio": Decimal("0.25"),
                "operating_band_orange_dlq_pressure_ratio": Decimal("0.50"),
                "operating_band_red_dlq_pressure_ratio": Decimal("1.0"),
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

        async def get_reprocessing_queue_health(self):
            now = datetime.now(UTC)
            return {
                "as_of": now,
                "total_pending_jobs": 4,
                "total_processing_jobs": 1,
                "total_failed_jobs": 0,
                "queues": [
                    {
                        "job_type": "RESET_WATERMARKS",
                        "pending_jobs": 4,
                        "processing_jobs": 1,
                        "failed_jobs": 0,
                        "oldest_pending_created_at": now,
                        "oldest_pending_age_seconds": 12.5,
                    }
                ],
            }

        async def get_capacity_status(
            self,
            *,
            lookback_minutes: int = 60,
            limit: int = 200,
            assumed_replicas: int = 1,
        ):
            now = datetime.now(UTC)
            return {
                "as_of": now,
                "lookback_minutes": lookback_minutes,
                "assumed_replicas": assumed_replicas,
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
                        "lambda_in_events_per_second": Decimal("0.333333"),
                        "mu_msg_per_replica_events_per_second": Decimal("0.250000"),
                        "assumed_replicas": assumed_replicas,
                        "effective_capacity_events_per_second": Decimal("0.500000"),
                        "utilization_ratio": Decimal("0.666666"),
                        "headroom_ratio": Decimal("0.333334"),
                        "estimated_drain_seconds": 1800.0,
                        "saturation_state": "stable",
                    }
                ][:limit],
            }

        async def find_successful_replay_audit_by_fingerprint(
            self,
            replay_fingerprint: str,
            recovery_path: str | None = None,
        ) -> dict[str, str] | None:
            row = self.replay_audit.get(replay_fingerprint)
            if (
                row
                and row.get("replay_status") in {"replayed", "replayed_bookkeeping_failed"}
                and (recovery_path is None or row.get("recovery_path") == recovery_path)
            ):
                return {
                    "replay_id": row["replay_id"],
                    "replay_status": row["replay_status"],
                }
            return None

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
        ) -> str:
            replay_id = f"replay_test_{len(self.replay_audit) + 1}"
            self.replay_audit[replay_fingerprint] = {
                "replay_id": replay_id,
                "recovery_path": recovery_path,
                "event_id": event_id,
                "replay_fingerprint": replay_fingerprint,
                "correlation_id": correlation_id,
                "job_id": job_id,
                "endpoint": endpoint,
                "replay_status": replay_status,
                "dry_run": dry_run,
                "replay_reason": replay_reason,
                "requested_by": requested_by,
                "requested_at": datetime.now(UTC),
                "completed_at": datetime.now(UTC),
            }
            return replay_id

        async def list_replay_audits(
            self,
            *,
            limit: int = 100,
            recovery_path: str | None = None,
            replay_status: str | None = None,
            replay_fingerprint: str | None = None,
            job_id: str | None = None,
        ) -> list[dict]:
            rows = list(self.replay_audit.values())
            filtered = [
                row
                for row in rows
                if (recovery_path is None or row.get("recovery_path") == recovery_path)
                and (replay_status is None or row.get("replay_status") == replay_status)
                and (
                    replay_fingerprint is None
                    or row.get("replay_fingerprint") == replay_fingerprint
                )
                and (job_id is None or row.get("job_id") == job_id)
            ]
            return filtered[:limit]

        async def get_replay_audit(self, replay_id: str):
            for row in self.replay_audit.values():
                if row.get("replay_id") == replay_id:
                    return row
            return None

        async def get_ops_mode(self):
            return {
                "mode": self.mode,
                "replay_window_start": self.replay_window_start,
                "replay_window_end": self.replay_window_end,
                "updated_by": "test",
                "updated_at": datetime.now(UTC),
            }

        async def update_ops_mode(
            self,
            *,
            mode: str,
            replay_window_start: datetime | None,
            replay_window_end: datetime | None,
            updated_by: str | None,
        ):
            self.mode = mode
            self.replay_window_start = replay_window_start
            self.replay_window_end = replay_window_end
            return {
                "mode": self.mode,
                "replay_window_start": self.replay_window_start,
                "replay_window_end": self.replay_window_end,
                "updated_by": updated_by,
                "updated_at": datetime.now(UTC),
            }

        async def assert_ingestion_writable(self) -> None:
            if self.mode in {"paused", "drain"}:
                raise PermissionError(
                    f"Ingestion is currently in '{self.mode}' mode and not accepting new requests."
                )

        async def assert_retry_allowed(self, submitted_at: datetime) -> None:
            if self.mode == "paused":
                raise PermissionError("Retries are blocked while ingestion is paused.")

        async def assert_retry_allowed_for_records(
            self,
            *,
            submitted_at: datetime,
            replay_record_count: int,
        ) -> None:
            await self.assert_retry_allowed(submitted_at)

        async def assert_reprocessing_publish_allowed(self, record_count: int) -> None:
            if not self.reprocessing_publish_allowed:
                raise PermissionError(
                    f"Reprocessing publication is blocked for {record_count} record(s)."
                )
            return None

    class FakeReferenceDataIngestionService:
        def __init__(self):
            self.persisted: dict[str, list[dict]] = {
                "benchmark_assignments": [],
                "benchmark_definitions": [],
            }

        async def upsert_portfolio_benchmark_assignments(
            self, records: list[dict[str, object]]
        ) -> None:
            now = datetime.now(UTC)
            normalized = []
            for record in records:
                row = dict(record)
                if row.get("assignment_recorded_at") is None:
                    row["assignment_recorded_at"] = now
                normalized.append(row)
            self.persisted["benchmark_assignments"].extend(normalized)

        async def upsert_benchmark_definitions(self, records: list[dict[str, object]]) -> None:
            self.persisted["benchmark_definitions"].extend(records)

        async def upsert_benchmark_compositions(self, records: list[dict[str, object]]) -> None:
            return None

        async def upsert_indices(self, records: list[dict[str, object]]) -> None:
            return None

        async def upsert_index_price_series(self, records: list[dict[str, object]]) -> None:
            return None

        async def upsert_index_return_series(self, records: list[dict[str, object]]) -> None:
            return None

        async def upsert_benchmark_return_series(self, records: list[dict[str, object]]) -> None:
            return None

        async def upsert_risk_free_series(self, records: list[dict[str, object]]) -> None:
            return None

        async def upsert_classification_taxonomy(self, records: list[dict[str, object]]) -> None:
            return None

        async def upsert_cash_account_masters(self, records: list[dict[str, object]]) -> None:
            return None

        async def upsert_instrument_lookthrough_components(
            self, records: list[dict[str, object]]
        ) -> None:
            return None

    class FakeBusinessCalendarRepository:
        def __init__(self):
            self.latest_business_dates = {}

        async def get_latest_business_date(self, calendar_code: str):
            return self.latest_business_dates.get(calendar_code)

    fake_job_service = FakeIngestionJobService()
    fake_reference_data_service = FakeReferenceDataIngestionService()
    fake_business_calendar_repository = FakeBusinessCalendarRepository()
    target_apps = (app, event_replay_app)

    for target_app in target_apps:
        target_app.dependency_overrides[get_ingestion_job_service] = lambda: fake_job_service
        target_app.dependency_overrides[get_kafka_producer] = override_get_kafka_producer

    app.dependency_overrides[transactions_router.get_ingestion_job_service] = lambda: (
        fake_job_service
    )
    app.dependency_overrides[portfolios_router.get_ingestion_job_service] = lambda: fake_job_service
    app.dependency_overrides[instruments_router.get_ingestion_job_service] = lambda: (
        fake_job_service
    )
    app.dependency_overrides[market_prices_router.get_ingestion_job_service] = lambda: (
        fake_job_service
    )
    app.dependency_overrides[fx_rates_router.get_ingestion_job_service] = lambda: fake_job_service
    app.dependency_overrides[business_dates_router.get_ingestion_job_service] = lambda: (
        fake_job_service
    )
    app.dependency_overrides[business_dates_router.get_business_calendar_repository] = lambda: (
        fake_business_calendar_repository
    )
    app.dependency_overrides[portfolio_bundle_router.get_ingestion_job_service] = lambda: (
        fake_job_service
    )
    app.dependency_overrides[reprocessing_router.get_ingestion_job_service] = lambda: (
        fake_job_service
    )
    app.dependency_overrides[reference_data_router.get_ingestion_job_service] = lambda: (
        fake_job_service
    )
    app.dependency_overrides[reference_data_router.get_reference_data_ingestion_service] = lambda: (
        fake_reference_data_service
    )
    event_replay_app.dependency_overrides[ingestion_operations_router.get_ingestion_job_service] = (
        lambda: fake_job_service
    )

    yield {
        "fake_job_service": fake_job_service,
        "fake_reference_data_service": fake_reference_data_service,
        "fake_business_calendar_repository": fake_business_calendar_repository,
    }

    for target_app in target_apps:
        target_app.dependency_overrides.pop(get_kafka_producer, None)
        target_app.dependency_overrides.pop(get_ingestion_job_service, None)
    app.dependency_overrides.pop(transactions_router.get_ingestion_job_service, None)
    app.dependency_overrides.pop(portfolios_router.get_ingestion_job_service, None)
    app.dependency_overrides.pop(instruments_router.get_ingestion_job_service, None)
    app.dependency_overrides.pop(market_prices_router.get_ingestion_job_service, None)
    app.dependency_overrides.pop(fx_rates_router.get_ingestion_job_service, None)
    app.dependency_overrides.pop(business_dates_router.get_ingestion_job_service, None)
    app.dependency_overrides.pop(
        business_dates_router.get_business_calendar_repository,
        None,
    )
    app.dependency_overrides.pop(portfolio_bundle_router.get_ingestion_job_service, None)
    app.dependency_overrides.pop(reprocessing_router.get_ingestion_job_service, None)
    app.dependency_overrides.pop(reference_data_router.get_ingestion_job_service, None)
    app.dependency_overrides.pop(
        reference_data_router.get_reference_data_ingestion_service,
        None,
    )
    event_replay_app.dependency_overrides.pop(
        ingestion_operations_router.get_ingestion_job_service,
        None,
    )


@pytest_asyncio.fixture
async def async_test_client(ingestion_test_harness):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Lotus-Ops-Token": "lotus-core-ops-local"},
    ) as client:
        yield client


@pytest_asyncio.fixture
async def event_replay_test_client(ingestion_test_harness):
    transport = httpx.ASGITransport(app=event_replay_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Lotus-Ops-Token": "lotus-core-ops-local"},
    ) as client:
        yield client


def _single_transaction_payload(transaction_id: str = "TX_SINGLE_001") -> dict[str, object]:
    return {
        "transaction_id": transaction_id,
        "portfolio_id": "P1",
        "instrument_id": "I1",
        "security_id": "S1",
        "transaction_date": "2025-08-12T10:00:00Z",
        "transaction_type": "BUY",
        "quantity": 1,
        "price": 1,
        "gross_transaction_amount": 1,
        "trade_currency": "USD",
        "currency": "USD",
    }


def _transaction_batch_payload(*transaction_ids: str) -> dict[str, list[dict[str, object]]]:
    ids = transaction_ids or ("TX_BATCH_001",)
    return {"transactions": [_single_transaction_payload(transaction_id) for transaction_id in ids]}


def _instrument_batch_payload(*security_ids: str) -> dict[str, list[dict[str, object]]]:
    ids = security_ids or ("SEC_INST_001",)
    return {
        "instruments": [
            {
                "security_id": security_id,
                "name": f"Instrument {security_id}",
                "isin": f"ISIN{security_id[-6:]}",
                "currency": "USD",
                "product_type": "bond",
            }
            for security_id in ids
        ]
    }


def _market_price_batch_payload(*security_ids: str) -> dict[str, list[dict[str, object]]]:
    ids = security_ids or ("SEC_PRICE_001",)
    return {
        "market_prices": [
            {
                "security_id": security_id,
                "price_date": "2025-01-01",
                "price": 100,
                "currency": "USD",
            }
            for security_id in ids
        ]
    }


def _fx_rate_batch_payload(*pairs: tuple[str, str]) -> dict[str, list[dict[str, object]]]:
    requested_pairs = pairs or (("USD", "SGD"),)
    return {
        "fx_rates": [
            {
                "from_currency": from_currency,
                "to_currency": to_currency,
                "rate_date": "2025-01-01",
                "rate": "1.3500000000",
            }
            for from_currency, to_currency in requested_pairs
        ]
    }


def _business_date_batch_payload(*business_dates: str) -> dict[str, list[dict[str, object]]]:
    dates = business_dates or ("2025-01-01",)
    return {
        "business_dates": [
            {
                "business_date": business_date,
                "calendar_code": "GLOBAL",
                "market_code": "XSWX",
                "source_system": "lotus-manage",
                "source_batch_id": "business-dates-certification",
            }
            for business_date in dates
        ]
    }


def _portfolio_bundle_payload() -> dict[str, object]:
    return {
        "source_system": "UI_UPLOAD",
        "mode": "UPSERT",
        "business_dates": [{"business_date": "2026-01-02"}],
        "portfolios": [
            {
                "portfolio_id": "P1",
                "base_currency": "USD",
                "open_date": "2025-01-01",
                "client_id": "c",
                "status": "s",
                "risk_exposure": "r",
                "investment_time_horizon": "i",
                "portfolio_type": "t",
                "booking_center_code": "b",
            }
        ],
        "instruments": [
            {
                "security_id": "S1",
                "name": "N1",
                "isin": "I1",
                "currency": "USD",
                "product_type": "E",
            }
        ],
        "transactions": [
            {
                "transaction_id": "T1",
                "portfolio_id": "P1",
                "instrument_id": "I1",
                "security_id": "S1",
                "transaction_date": "2026-01-02T10:00:00Z",
                "transaction_type": "BUY",
                "quantity": 1,
                "price": 1,
                "gross_transaction_amount": 1,
                "trade_currency": "USD",
                "currency": "USD",
            }
        ],
        "market_prices": [
            {"security_id": "S1", "price_date": "2026-01-02", "price": 100, "currency": "USD"}
        ],
        "fx_rates": [
            {"from_currency": "USD", "to_currency": "EUR", "rate_date": "2026-01-02", "rate": 0.9}
        ],
    }


async def test_ingest_portfolios_endpoint(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    """Tests the POST /ingest/portfolios endpoint."""
    mock_kafka_producer.publish_message.reset_mock()
    payload = {
        "portfolios": [
            {
                "portfolio_id": "P1",
                "base_currency": "USD",
                "open_date": "2025-01-01",
                "client_id": "c",
                "status": "s",
                "risk_exposure": "r",
                "investment_time_horizon": "i",
                "portfolio_type": "t",
                "booking_center_code": "b",
            }
        ]
    }

    response = await async_test_client.post("/ingest/portfolios", json=payload)

    assert response.status_code == 202
    body = response.json()
    assert body["message"] == "Portfolios accepted for asynchronous ingestion processing."
    assert body["entity_type"] == "portfolio"
    assert body["accepted_count"] == 1
    assert body["job_id"]
    assert body["correlation_id"]
    assert body["request_id"]
    assert body["trace_id"]
    mock_kafka_producer.publish_message.assert_called_once()


async def test_ingest_portfolios_replays_duplicate_idempotency_key(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    mock_kafka_producer.publish_message.reset_mock()
    payload = {
        "portfolios": [
            {
                "portfolio_id": "P1",
                "base_currency": "USD",
                "open_date": "2025-01-01",
                "client_id": "c",
                "status": "active",
                "risk_exposure": "balanced",
                "investment_time_horizon": "long_term",
                "portfolio_type": "discretionary",
                "booking_center_code": "SG_BOOKING",
            }
        ]
    }
    headers = {"X-Idempotency-Key": "portfolio-master-replay-001"}

    first = await async_test_client.post("/ingest/portfolios", json=payload, headers=headers)
    second = await async_test_client.post("/ingest/portfolios", json=payload, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert (
        second.json()["message"] == "Duplicate ingestion request accepted via idempotency replay."
    )
    assert second.json()["job_id"] == first.json()["job_id"]
    assert second.json()["idempotency_key"] == "portfolio-master-replay-001"
    mock_kafka_producer.publish_message.assert_called_once()


async def test_ingest_portfolios_returns_503_when_mode_blocks_writes(
    async_test_client: httpx.AsyncClient,
    ingestion_test_harness,
    mock_kafka_producer: MagicMock,
):
    ingestion_test_harness["fake_job_service"].mode = "paused"

    response = await async_test_client.post(
        "/ingest/portfolios",
        json={
            "portfolios": [
                {
                    "portfolio_id": "P1",
                    "base_currency": "USD",
                    "open_date": "2025-01-01",
                    "client_id": "c",
                    "status": "active",
                    "risk_exposure": "balanced",
                    "investment_time_horizon": "long_term",
                    "portfolio_type": "discretionary",
                    "booking_center_code": "SG_BOOKING",
                }
            ]
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "INGESTION_MODE_BLOCKS_WRITES"
    mock_kafka_producer.publish_message.assert_not_called()


async def test_ingest_portfolios_returns_429_when_rate_limited(
    async_test_client: httpx.AsyncClient,
    monkeypatch,
    mock_kafka_producer: MagicMock,
):
    def _raise_rate_limit(*, endpoint: str, record_count: int) -> None:
        raise PermissionError(f"{endpoint} blocked after {record_count} records")

    monkeypatch.setattr(
        portfolios_router,
        "enforce_ingestion_write_rate_limit",
        _raise_rate_limit,
    )

    response = await async_test_client.post(
        "/ingest/portfolios",
        json={
            "portfolios": [
                {
                    "portfolio_id": "P1",
                    "base_currency": "USD",
                    "open_date": "2025-01-01",
                    "client_id": "c",
                    "status": "active",
                    "risk_exposure": "balanced",
                    "investment_time_horizon": "long_term",
                    "portfolio_type": "discretionary",
                    "booking_center_code": "SG_BOOKING",
                }
            ]
        },
    )

    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "INGESTION_RATE_LIMIT_EXCEEDED"
    mock_kafka_producer.publish_message.assert_not_called()


async def test_ingest_portfolios_marks_job_failed_when_publish_fails(
    async_test_client: httpx.AsyncClient,
    event_replay_test_client: httpx.AsyncClient,
    mock_kafka_producer: MagicMock,
):
    mock_kafka_producer.publish_message.side_effect = RuntimeError("broker timeout")

    payload = {
        "portfolios": [
            {
                "portfolio_id": "P1",
                "base_currency": "USD",
                "open_date": "2025-01-01",
                "client_id": "c",
                "status": "active",
                "risk_exposure": "balanced",
                "investment_time_horizon": "long_term",
                "portfolio_type": "discretionary",
                "booking_center_code": "SG_BOOKING",
            },
            {
                "portfolio_id": "P2",
                "base_currency": "EUR",
                "open_date": "2025-01-01",
                "client_id": "c",
                "status": "active",
                "risk_exposure": "conservative",
                "investment_time_horizon": "medium_term",
                "portfolio_type": "advisory",
                "booking_center_code": "EU_BOOKING",
            },
        ]
    }

    with pytest.raises(Exception, match="Failed to publish portfolio"):
        await async_test_client.post("/ingest/portfolios", json=payload)

    jobs_response = await event_replay_test_client.get(
        "/ingestion/jobs",
        params={"status": "failed", "entity_type": "portfolio"},
    )
    assert jobs_response.status_code == 200
    failed_job_id = jobs_response.json()["jobs"][0]["job_id"]

    failure_history = await event_replay_test_client.get(
        f"/ingestion/jobs/{failed_job_id}/failures"
    )
    assert failure_history.status_code == 200
    assert failure_history.json()["failures"][0]["failed_record_keys"] == ["P1", "P2"]


async def test_ingest_single_transaction_endpoint(
    async_test_client: httpx.AsyncClient,
    ingestion_test_harness,
    mock_kafka_producer: MagicMock,
):
    mock_kafka_producer.publish_message.reset_mock()

    response = await async_test_client.post(
        "/ingest/transaction",
        json=_single_transaction_payload("TX_SINGLE_ACK_001"),
        headers={"X-Idempotency-Key": "single-transaction-idem-001"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["message"] == "Transaction accepted for asynchronous ingestion processing."
    assert body["entity_type"] == "transaction"
    assert body["accepted_count"] == 1
    assert body["idempotency_key"] == "single-transaction-idem-001"
    assert body["correlation_id"]
    assert body["request_id"]
    assert body["trace_id"]
    assert "job_id" not in body
    assert ingestion_test_harness["fake_job_service"].jobs == {}

    mock_kafka_producer.publish_message.assert_called_once()
    publish_kwargs = mock_kafka_producer.publish_message.call_args.kwargs
    assert publish_kwargs["topic"] == "transactions.raw.received"
    assert publish_kwargs["key"] == "P1"
    assert publish_kwargs["value"]["transaction_id"] == "TX_SINGLE_ACK_001"
    assert dict(publish_kwargs["headers"])["idempotency_key"] == (b"single-transaction-idem-001")


async def test_ingest_single_transaction_returns_503_when_mode_blocks_writes(
    async_test_client: httpx.AsyncClient,
    ingestion_test_harness,
    mock_kafka_producer: MagicMock,
):
    ingestion_test_harness["fake_job_service"].mode = "paused"

    response = await async_test_client.post(
        "/ingest/transaction",
        json=_single_transaction_payload("TX_SINGLE_BLOCKED_001"),
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "INGESTION_MODE_BLOCKS_WRITES"
    mock_kafka_producer.publish_message.assert_not_called()


async def test_ingest_single_transaction_returns_429_when_rate_limited(
    async_test_client: httpx.AsyncClient,
    monkeypatch,
    mock_kafka_producer: MagicMock,
):
    def _raise_rate_limit(*, endpoint: str, record_count: int) -> None:
        raise PermissionError(f"{endpoint} blocked after {record_count} records")

    monkeypatch.setattr(
        transactions_router,
        "enforce_ingestion_write_rate_limit",
        _raise_rate_limit,
    )

    response = await async_test_client.post(
        "/ingest/transaction",
        json=_single_transaction_payload("TX_SINGLE_RATE_LIMIT_001"),
    )

    assert response.status_code == 429
    assert response.json()["detail"] == {
        "code": "INGESTION_RATE_LIMIT_EXCEEDED",
        "message": "/ingest/transaction blocked after 1 records",
    }
    mock_kafka_producer.publish_message.assert_not_called()


async def test_ingest_single_transaction_returns_failed_record_keys_when_publish_fails(
    async_test_client: httpx.AsyncClient,
    mock_kafka_producer: MagicMock,
):
    mock_kafka_producer.publish_message.side_effect = RuntimeError("broker timeout")

    response = await async_test_client.post(
        "/ingest/transaction",
        json=_single_transaction_payload("TX_SINGLE_PUBLISH_FAIL_001"),
    )

    assert response.status_code == 500
    assert response.json()["detail"] == {
        "code": "INGESTION_PUBLISH_FAILED",
        "message": "Failed to publish transaction 'TX_SINGLE_PUBLISH_FAIL_001'.",
        "failed_record_keys": ["TX_SINGLE_PUBLISH_FAIL_001"],
    }


async def test_ingest_transactions_endpoint(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    """Tests the POST /ingest/transactions endpoint."""
    mock_kafka_producer.publish_message.reset_mock()
    payload = _transaction_batch_payload("TX_BATCH_ACK_001")

    response = await async_test_client.post(
        "/ingest/transactions",
        json=payload,
        headers={"X-Idempotency-Key": "transaction-batch-idem-001"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["message"] == "Transactions accepted for asynchronous ingestion processing."
    assert body["entity_type"] == "transaction"
    assert body["accepted_count"] == 1
    assert body["job_id"]
    assert body["idempotency_key"] == "transaction-batch-idem-001"
    assert body["correlation_id"]
    assert body["request_id"]
    assert body["trace_id"]
    mock_kafka_producer.publish_message.assert_called_once()
    publish_kwargs = mock_kafka_producer.publish_message.call_args.kwargs
    assert publish_kwargs["topic"] == "transactions.raw.received"
    assert publish_kwargs["key"] == "P1"
    assert publish_kwargs["value"]["transaction_id"] == "TX_BATCH_ACK_001"
    assert dict(publish_kwargs["headers"])["idempotency_key"] == (b"transaction-batch-idem-001")


async def test_ingest_transactions_endpoint_accepts_empty_batch(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    mock_kafka_producer.publish_message.reset_mock()

    response = await async_test_client.post("/ingest/transactions", json={"transactions": []})

    assert response.status_code == 202
    body = response.json()
    assert body["entity_type"] == "transaction"
    assert body["accepted_count"] == 0
    assert "job_id" in body
    mock_kafka_producer.publish_message.assert_not_called()


async def test_ingestion_jobs_status_endpoint(
    async_test_client: httpx.AsyncClient,
    event_replay_test_client: httpx.AsyncClient,
    mock_kafka_producer: MagicMock,
):
    mock_kafka_producer.publish_message.reset_mock()
    payload = {
        "transactions": [
            {
                "transaction_id": "T100",
                "portfolio_id": "P1",
                "instrument_id": "I1",
                "security_id": "S1",
                "transaction_date": "2025-08-12T10:00:00Z",
                "transaction_type": "BUY",
                "quantity": 1,
                "price": 1,
                "gross_transaction_amount": 1,
                "trade_currency": "USD",
                "currency": "USD",
            }
        ]
    }

    ingest_response = await async_test_client.post("/ingest/transactions", json=payload)
    assert ingest_response.status_code == 202
    job_id = ingest_response.json()["job_id"]

    job_response = await event_replay_test_client.get(f"/ingestion/jobs/{job_id}")
    assert job_response.status_code == 200
    job_body = job_response.json()
    assert job_body["job_id"] == job_id
    assert job_body["status"] == "queued"
    assert job_body["entity_type"] == "transaction"


async def test_ingestion_jobs_list_endpoint(event_replay_test_client: httpx.AsyncClient):
    response = await event_replay_test_client.get("/ingestion/jobs", params={"limit": 5})
    assert response.status_code == 200
    body = response.json()
    assert "jobs" in body
    assert "total" in body
    assert "next_cursor" in body


async def test_ingestion_job_not_found(event_replay_test_client: httpx.AsyncClient):
    response = await event_replay_test_client.get("/ingestion/jobs/job_missing_001")
    assert response.status_code == 404
    body = response.json()
    assert body["detail"]["code"] == "INGESTION_JOB_NOT_FOUND"


async def test_ingestion_jobs_idempotency_replays_existing_job(
    async_test_client: httpx.AsyncClient,
    mock_kafka_producer: MagicMock,
):
    mock_kafka_producer.publish_message.reset_mock()
    payload = _transaction_batch_payload("TX_IDEMPOTENT_001")
    headers = {"X-Idempotency-Key": "idem-batch-001"}

    first = await async_test_client.post("/ingest/transactions", json=payload, headers=headers)
    second = await async_test_client.post("/ingest/transactions", json=payload, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]
    assert (
        second.json()["message"] == "Duplicate ingestion request accepted via idempotency replay."
    )
    assert second.json()["idempotency_key"] == "idem-batch-001"
    mock_kafka_producer.publish_message.assert_called_once()


async def test_ingest_transactions_returns_429_when_rate_limited(
    async_test_client: httpx.AsyncClient,
    monkeypatch,
    mock_kafka_producer: MagicMock,
):
    def _raise_rate_limit(*, endpoint: str, record_count: int) -> None:
        raise PermissionError(f"{endpoint} blocked after {record_count} records")

    monkeypatch.setattr(
        transactions_router,
        "enforce_ingestion_write_rate_limit",
        _raise_rate_limit,
    )

    response = await async_test_client.post(
        "/ingest/transactions",
        json=_transaction_batch_payload("TX_BATCH_RATE_LIMIT_001", "TX_BATCH_RATE_LIMIT_002"),
    )

    assert response.status_code == 429
    assert response.json()["detail"] == {
        "code": "INGESTION_RATE_LIMIT_EXCEEDED",
        "message": "/ingest/transactions blocked after 2 records",
    }
    mock_kafka_producer.publish_message.assert_not_called()


async def test_ingestion_job_failure_history_and_retry(
    async_test_client: httpx.AsyncClient,
    event_replay_test_client: httpx.AsyncClient,
    mock_kafka_producer: MagicMock,
):
    mock_kafka_producer.publish_message.side_effect = RuntimeError("broker timeout")
    payload = _transaction_batch_payload("TX_FAIL_001")

    failed_response = await async_test_client.post("/ingest/transactions", json=payload)
    assert failed_response.status_code == 500
    assert failed_response.json()["detail"]["code"] == "INGESTION_PUBLISH_FAILED"
    assert failed_response.json()["detail"]["failed_record_keys"] == ["TX_FAIL_001"]

    jobs_response = await event_replay_test_client.get(
        "/ingestion/jobs",
        params={"status": "failed"},
    )
    assert jobs_response.status_code == 200
    failed_job_id = jobs_response.json()["jobs"][0]["job_id"]

    failure_history = await event_replay_test_client.get(
        f"/ingestion/jobs/{failed_job_id}/failures"
    )
    assert failure_history.status_code == 200
    assert failure_history.json()["total"] >= 1
    assert failure_history.json()["failures"][0]["failed_record_keys"] == ["TX_FAIL_001"]

    mock_kafka_producer.publish_message.side_effect = None
    retry_response = await event_replay_test_client.post(f"/ingestion/jobs/{failed_job_id}/retry")
    assert retry_response.status_code == 200
    assert retry_response.json()["status"] == "queued"
    assert retry_response.json()["retry_count"] == 1


async def test_ingest_transactions_reports_bookkeeping_failure_after_publish(
    async_test_client: httpx.AsyncClient,
    event_replay_test_client: httpx.AsyncClient,
    ingestion_test_harness,
):
    ingestion_test_harness["fake_job_service"].fail_next_mark_queued = True
    payload = {
        "transactions": [
            {
                "transaction_id": "TX_BOOKKEEPING_FAIL_001",
                "portfolio_id": "P1",
                "instrument_id": "I1",
                "security_id": "S1",
                "transaction_date": "2025-08-12T10:00:00Z",
                "transaction_type": "BUY",
                "quantity": 1,
                "price": 1,
                "gross_transaction_amount": 1,
                "trade_currency": "USD",
                "currency": "USD",
            }
        ]
    }

    response = await async_test_client.post("/ingest/transactions", json=payload)

    assert response.status_code == 500
    body = response.json()
    assert body["detail"]["code"] == "INGESTION_JOB_BOOKKEEPING_FAILED"
    job_id = body["detail"]["job_id"]

    job = ingestion_test_harness["fake_job_service"].jobs[job_id]
    assert job.status == "accepted"

    failure_history = await event_replay_test_client.get(f"/ingestion/jobs/{job_id}/failures")
    assert failure_history.status_code == 200
    assert failure_history.json()["failures"][0]["failure_phase"] == "queue_bookkeeping"


async def test_reference_data_ingest_reports_bookkeeping_failure_after_persist(
    async_test_client: httpx.AsyncClient,
    event_replay_test_client: httpx.AsyncClient,
    ingestion_test_harness,
):
    ingestion_test_harness["fake_job_service"].fail_next_mark_queued = True
    payload = {
        "benchmark_definitions": [
            {
                "benchmark_id": "BMK_WORLD_60_40",
                "benchmark_name": "World 60/40",
                "benchmark_type": "composite",
                "benchmark_currency": "USD",
                "return_convention": "total_return_index",
                "effective_from": "2025-01-01",
            }
        ]
    }

    response = await async_test_client.post("/ingest/benchmark-definitions", json=payload)

    assert response.status_code == 500
    body = response.json()
    assert body["detail"]["code"] == "INGESTION_JOB_BOOKKEEPING_FAILED"
    job_id = body["detail"]["job_id"]

    persisted = ingestion_test_harness["fake_reference_data_service"].persisted[
        "benchmark_definitions"
    ]
    assert len(persisted) == 1
    assert persisted[0]["benchmark_id"] == "BMK_WORLD_60_40"

    job = ingestion_test_harness["fake_job_service"].jobs[job_id]
    assert job.status == "accepted"

    failure_history = await event_replay_test_client.get(f"/ingestion/jobs/{job_id}/failures")
    assert failure_history.status_code == 200
    assert failure_history.json()["failures"][0]["failure_phase"] == "persist_bookkeeping"


async def test_ingest_benchmark_assignments_defaults_assignment_recorded_at_when_omitted(
    async_test_client: httpx.AsyncClient,
    ingestion_test_harness,
):
    payload = {
        "benchmark_assignments": [
            {
                "portfolio_id": "LIVE_REAL_005607",
                "benchmark_id": "BMK_US_60_40_005607",
                "effective_from": "2026-01-01",
                "assignment_source": "benchmark_policy_engine",
                "assignment_status": "active",
                "source_system": "lotus-manage",
            }
        ]
    }

    response = await async_test_client.post("/ingest/benchmark-assignments", json=payload)

    assert response.status_code == 202
    persisted = ingestion_test_harness["fake_reference_data_service"].persisted[
        "benchmark_assignments"
    ]
    assert len(persisted) == 1
    assert persisted[0]["assignment_recorded_at"] is not None


async def test_ingestion_job_retry_reports_bookkeeping_failure_after_replay_publish(
    async_test_client: httpx.AsyncClient,
    event_replay_test_client: httpx.AsyncClient,
    ingestion_test_harness,
    mock_kafka_producer: MagicMock,
):
    mock_kafka_producer.publish_message.side_effect = RuntimeError("broker timeout")
    payload = {
        "transactions": [
            {
                "transaction_id": "TX_RETRY_BOOKKEEPING_001",
                "portfolio_id": "P1",
                "instrument_id": "I1",
                "security_id": "S1",
                "transaction_date": "2025-08-12T10:00:00Z",
                "transaction_type": "BUY",
                "quantity": 1,
                "price": 1,
                "gross_transaction_amount": 1,
                "trade_currency": "USD",
                "currency": "USD",
            }
        ]
    }

    with pytest.raises(Exception, match="Failed to publish transaction"):
        await async_test_client.post("/ingest/transactions", json=payload)

    jobs_response = await event_replay_test_client.get(
        "/ingestion/jobs",
        params={"status": "failed"},
    )
    failed_job_id = jobs_response.json()["jobs"][0]["job_id"]

    ingestion_test_harness["fake_job_service"].fail_mark_queued_job_ids.add(failed_job_id)
    mock_kafka_producer.publish_message.side_effect = None

    retry_response = await event_replay_test_client.post(f"/ingestion/jobs/{failed_job_id}/retry")

    assert retry_response.status_code == 500
    body = retry_response.json()
    assert body["detail"]["code"] == "INGESTION_RETRY_BOOKKEEPING_FAILED"
    assert body["detail"]["replay_audit_id"]
    assert body["detail"]["replay_fingerprint"]

    audit_response = await event_replay_test_client.get(
        "/ingestion/audit/replays",
        params={"job_id": failed_job_id},
    )
    audits = audit_response.json()["audits"]
    assert any(row["replay_status"] == "replayed_bookkeeping_failed" for row in audits)

    ingestion_test_harness["fake_job_service"].fail_mark_queued_job_ids.discard(failed_job_id)
    duplicate_response = await event_replay_test_client.post(
        f"/ingestion/jobs/{failed_job_id}/retry"
    )
    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["detail"]["code"] == "INGESTION_RETRY_DUPLICATE_BLOCKED"


async def test_ingestion_job_failure_history_tracks_remaining_unpublished_batch_keys(
    async_test_client: httpx.AsyncClient,
    event_replay_test_client: httpx.AsyncClient,
    mock_kafka_producer: MagicMock,
):
    mock_kafka_producer.publish_message.side_effect = [None, RuntimeError("broker timeout")]
    payload = {
        "transactions": [
            {
                "transaction_id": "TX_BATCH_FAIL_001",
                "portfolio_id": "P1",
                "instrument_id": "I1",
                "security_id": "S1",
                "transaction_date": "2025-08-12T10:00:00Z",
                "transaction_type": "BUY",
                "quantity": 1,
                "price": 1,
                "gross_transaction_amount": 1,
                "trade_currency": "USD",
                "currency": "USD",
            },
            {
                "transaction_id": "TX_BATCH_FAIL_002",
                "portfolio_id": "P1",
                "instrument_id": "I1",
                "security_id": "S1",
                "transaction_date": "2025-08-12T10:01:00Z",
                "transaction_type": "BUY",
                "quantity": 1,
                "price": 1,
                "gross_transaction_amount": 1,
                "trade_currency": "USD",
                "currency": "USD",
            },
            {
                "transaction_id": "TX_BATCH_FAIL_003",
                "portfolio_id": "P1",
                "instrument_id": "I1",
                "security_id": "S1",
                "transaction_date": "2025-08-12T10:02:00Z",
                "transaction_type": "BUY",
                "quantity": 1,
                "price": 1,
                "gross_transaction_amount": 1,
                "trade_currency": "USD",
                "currency": "USD",
            },
        ]
    }

    with pytest.raises(Exception, match="Failed to publish transaction"):
        await async_test_client.post("/ingest/transactions", json=payload)

    jobs_response = await event_replay_test_client.get(
        "/ingestion/jobs",
        params={"status": "failed"},
    )
    assert jobs_response.status_code == 200
    failed_job_id = jobs_response.json()["jobs"][0]["job_id"]

    failure_history = await event_replay_test_client.get(
        f"/ingestion/jobs/{failed_job_id}/failures"
    )
    assert failure_history.status_code == 200
    assert failure_history.json()["failures"][0]["failed_record_keys"] == [
        "TX_BATCH_FAIL_002",
        "TX_BATCH_FAIL_003",
    ]


async def test_ingestion_job_partial_retry_dry_run(
    async_test_client: httpx.AsyncClient,
    event_replay_test_client: httpx.AsyncClient,
    mock_kafka_producer: MagicMock,
):
    payload = {
        "transactions": [
            {
                "transaction_id": "TX_PARTIAL_001",
                "portfolio_id": "P1",
                "instrument_id": "I1",
                "security_id": "S1",
                "transaction_date": "2025-08-12T10:00:00Z",
                "transaction_type": "BUY",
                "quantity": 1,
                "price": 1,
                "gross_transaction_amount": 1,
                "trade_currency": "USD",
                "currency": "USD",
            },
            {
                "transaction_id": "TX_PARTIAL_002",
                "portfolio_id": "P1",
                "instrument_id": "I2",
                "security_id": "S2",
                "transaction_date": "2025-08-12T10:00:00Z",
                "transaction_type": "BUY",
                "quantity": 1,
                "price": 1,
                "gross_transaction_amount": 1,
                "trade_currency": "USD",
                "currency": "USD",
            },
        ]
    }
    ingest_response = await async_test_client.post("/ingest/transactions", json=payload)
    assert ingest_response.status_code == 202
    job_id = ingest_response.json()["job_id"]

    dry_run = await event_replay_test_client.post(
        f"/ingestion/jobs/{job_id}/retry",
        json={"record_keys": ["TX_PARTIAL_002"], "dry_run": True},
    )
    assert dry_run.status_code == 200


async def test_ingestion_job_retry_blocks_duplicate_fingerprint(
    async_test_client: httpx.AsyncClient,
    event_replay_test_client: httpx.AsyncClient,
):
    payload = {
        "transactions": [
            {
                "transaction_id": "TX_RETRY_DUP_001",
                "portfolio_id": "P1",
                "instrument_id": "I1",
                "security_id": "S1",
                "transaction_date": "2025-08-12T10:00:00Z",
                "transaction_type": "BUY",
                "quantity": 1,
                "price": 1,
                "gross_transaction_amount": 1,
                "trade_currency": "USD",
                "currency": "USD",
            }
        ]
    }
    ingest_response = await async_test_client.post("/ingest/transactions", json=payload)
    assert ingest_response.status_code == 202
    job_id = ingest_response.json()["job_id"]
    first = await event_replay_test_client.post(
        f"/ingestion/jobs/{job_id}/retry",
        json={"dry_run": False},
    )
    assert first.status_code == 200
    second = await event_replay_test_client.post(
        f"/ingestion/jobs/{job_id}/retry",
        json={"dry_run": False},
    )
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "INGESTION_RETRY_DUPLICATE_BLOCKED"


async def test_ingestion_health_summary(event_replay_test_client: httpx.AsyncClient):
    response = await event_replay_test_client.get("/ingestion/health/summary")
    assert response.status_code == 200
    body = response.json()
    assert "total_jobs" in body
    assert "backlog_jobs" in body


async def test_ingestion_slo_status(event_replay_test_client: httpx.AsyncClient):
    response = await event_replay_test_client.get("/ingestion/health/slo")
    assert response.status_code == 200
    body = response.json()
    assert "failure_rate" in body
    assert "p95_queue_latency_seconds" in body


async def test_ingestion_backlog_breakdown(event_replay_test_client: httpx.AsyncClient):
    response = await event_replay_test_client.get("/ingestion/health/backlog-breakdown")
    assert response.status_code == 200
    body = response.json()
    assert "groups" in body
    assert "total_backlog_jobs" in body
    assert "largest_group_backlog_share" in body
    assert "top_3_backlog_share" in body
    assert body["groups"][0]["endpoint"] == "/ingest/transactions"


async def test_ingestion_stalled_jobs(event_replay_test_client: httpx.AsyncClient):
    response = await event_replay_test_client.get("/ingestion/health/stalled-jobs")
    assert response.status_code == 200
    body = response.json()
    assert "jobs" in body
    assert "threshold_seconds" in body
    assert body["jobs"][0]["status"] == "accepted"


async def test_ingestion_ops_control_mode_blocks_writes(
    async_test_client: httpx.AsyncClient,
    event_replay_test_client: httpx.AsyncClient,
):
    update_response = await event_replay_test_client.put(
        "/ingestion/ops/control",
        json={"mode": "paused", "updated_by": "test"},
    )
    assert update_response.status_code == 200

    payload = {
        "transactions": [
            {
                "transaction_id": "TX_BLOCKED_001",
                "portfolio_id": "P1",
                "instrument_id": "I1",
                "security_id": "S1",
                "transaction_date": "2025-08-12T10:00:00Z",
                "transaction_type": "BUY",
                "quantity": 1,
                "price": 1,
                "gross_transaction_amount": 1,
                "trade_currency": "USD",
                "currency": "USD",
            }
        ]
    }
    blocked = await async_test_client.post("/ingest/transactions", json=payload)
    assert blocked.status_code == 503

    restore_response = await event_replay_test_client.put(
        "/ingestion/ops/control",
        json={"mode": "normal", "updated_by": "test"},
    )
    assert restore_response.status_code == 200


async def test_ingestion_consumer_dlq_events_endpoint(event_replay_test_client: httpx.AsyncClient):
    response = await event_replay_test_client.get("/ingestion/dlq/consumer-events")
    assert response.status_code == 200
    body = response.json()
    assert "events" in body
    assert "total" in body


async def test_ingestion_consumer_lag_endpoint(event_replay_test_client: httpx.AsyncClient):
    response = await event_replay_test_client.get("/ingestion/health/consumer-lag")
    assert response.status_code == 200
    body = response.json()
    assert "groups" in body
    assert "backlog_jobs" in body


async def test_ingestion_error_budget_endpoint(event_replay_test_client: httpx.AsyncClient):
    response = await event_replay_test_client.get("/ingestion/health/error-budget")
    assert response.status_code == 200
    body = response.json()
    assert "failure_rate" in body
    assert "remaining_error_budget" in body
    assert "replay_backlog_pressure_ratio" in body
    assert "dlq_events_in_window" in body
    assert "dlq_budget_events_per_window" in body
    assert "dlq_pressure_ratio" in body


async def test_ingestion_operating_band_endpoint(event_replay_test_client: httpx.AsyncClient):
    response = await event_replay_test_client.get("/ingestion/health/operating-band")
    assert response.status_code == 200
    body = response.json()
    assert body["operating_band"] in {"green", "yellow", "orange", "red"}
    assert "recommended_action" in body
    assert "triggered_signals" in body


async def test_ingestion_operating_policy_endpoint(event_replay_test_client: httpx.AsyncClient):
    response = await event_replay_test_client.get("/ingestion/health/policy")
    assert response.status_code == 200
    body = response.json()
    assert body["policy_version"] == "v1"
    assert body["policy_fingerprint"]
    assert "lookback_minutes_default" in body
    assert "replay_max_records_per_request" in body
    assert "reprocessing_worker_batch_size" in body
    assert "valuation_scheduler_dispatch_rounds" in body
    assert "operating_band_red_backlog_age_seconds" in body
    assert "calculator_peak_lag_age_seconds" in body
    assert body["replay_isolation_mode"] in {"shared_workers", "dedicated_workers"}
    assert body["partition_growth_strategy"] in {
        "scale_out_only",
        "pre_shard_large_portfolios",
    }


async def test_ingestion_reprocessing_queue_health_endpoint(
    event_replay_test_client: httpx.AsyncClient,
):
    response = await event_replay_test_client.get("/ingestion/health/reprocessing-queue")
    assert response.status_code == 200
    body = response.json()
    assert "as_of" in body
    assert body["total_pending_jobs"] >= 0
    assert body["queues"][0]["job_type"] == "RESET_WATERMARKS"
    assert "oldest_pending_age_seconds" in body["queues"][0]


async def test_ingestion_capacity_status_endpoint(event_replay_test_client: httpx.AsyncClient):
    response = await event_replay_test_client.get(
        "/ingestion/health/capacity",
        params={"lookback_minutes": 60, "assumed_replicas": 2},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["lookback_minutes"] == 60
    assert body["assumed_replicas"] == 2
    assert body["total_backlog_records"] >= 0
    assert body["total_groups"] >= 1
    assert body["groups"][0]["endpoint"] == "/ingest/transactions"
    assert "lambda_in_events_per_second" in body["groups"][0]
    assert "mu_msg_per_replica_events_per_second" in body["groups"][0]
    assert body["groups"][0]["saturation_state"] in {
        "stable",
        "near_capacity",
        "over_capacity",
    }


async def test_ingestion_idempotency_diagnostics_endpoint(
    event_replay_test_client: httpx.AsyncClient,
):
    response = await event_replay_test_client.get("/ingestion/idempotency/diagnostics")
    assert response.status_code == 200
    body = response.json()
    assert "keys" in body
    assert "collisions" in body


async def test_ingestion_job_records_endpoint(
    async_test_client: httpx.AsyncClient,
    event_replay_test_client: httpx.AsyncClient,
):
    payload = {
        "transactions": [
            {
                "transaction_id": "TX_RECORD_001",
                "portfolio_id": "P1",
                "instrument_id": "I1",
                "security_id": "S1",
                "transaction_date": "2025-08-12T10:00:00Z",
                "transaction_type": "BUY",
                "quantity": 1,
                "price": 1,
                "gross_transaction_amount": 1,
                "trade_currency": "USD",
                "currency": "USD",
            }
        ]
    }
    ingest_response = await async_test_client.post("/ingest/transactions", json=payload)
    assert ingest_response.status_code == 202
    job_id = ingest_response.json()["job_id"]
    response = await event_replay_test_client.get(f"/ingestion/jobs/{job_id}/records")
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == job_id
    assert "replayable_record_keys" in body


async def test_replay_consumer_dlq_event_endpoint(
    async_test_client: httpx.AsyncClient,
    event_replay_test_client: httpx.AsyncClient,
):
    payload = {
        "transactions": [
            {
                "transaction_id": "TX_REPLAY_001",
                "portfolio_id": "P1",
                "instrument_id": "I1",
                "security_id": "S1",
                "transaction_date": "2025-08-12T10:00:00Z",
                "transaction_type": "BUY",
                "quantity": 1,
                "price": 1,
                "gross_transaction_amount": 1,
                "trade_currency": "USD",
                "currency": "USD",
            }
        ]
    }
    await async_test_client.post(
        "/ingest/transactions",
        headers={"X-Correlation-Id": "ING:test-correlation-id"},
        json=payload,
    )
    response = await event_replay_test_client.post(
        "/ingestion/dlq/consumer-events/cdlq_test_001/replay",
        json={"dry_run": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["replay_status"] in {"dry_run", "not_replayable", "replayed"}
    assert body.get("replay_audit_id")
    assert body.get("replay_fingerprint")


async def test_replay_consumer_dlq_event_blocks_duplicate_replay(
    async_test_client: httpx.AsyncClient,
    event_replay_test_client: httpx.AsyncClient,
):
    payload = {
        "transactions": [
            {
                "transaction_id": "TX_REPLAY_DUP_001",
                "portfolio_id": "P1",
                "instrument_id": "I1",
                "security_id": "S1",
                "transaction_date": "2025-08-12T10:00:00Z",
                "transaction_type": "BUY",
                "quantity": 1,
                "price": 1,
                "gross_transaction_amount": 1,
                "trade_currency": "USD",
                "currency": "USD",
            }
        ]
    }
    await async_test_client.post(
        "/ingest/transactions",
        headers={"X-Correlation-Id": "ING:test-correlation-id"},
        json=payload,
    )
    first = await event_replay_test_client.post(
        "/ingestion/dlq/consumer-events/cdlq_test_001/replay",
        json={"dry_run": False},
    )
    assert first.status_code == 200
    second = await event_replay_test_client.post(
        "/ingestion/dlq/consumer-events/cdlq_test_001/replay",
        json={"dry_run": False},
    )
    assert second.status_code == 200
    body = second.json()
    assert body["replay_status"] == "duplicate_blocked"


async def test_replay_consumer_dlq_event_reports_bookkeeping_failure_after_publish(
    async_test_client: httpx.AsyncClient,
    event_replay_test_client: httpx.AsyncClient,
    ingestion_test_harness,
):
    payload = {
        "transactions": [
            {
                "transaction_id": "TX_REPLAY_BOOKKEEPING_001",
                "portfolio_id": "P1",
                "instrument_id": "I1",
                "security_id": "S1",
                "transaction_date": "2025-08-12T10:00:00Z",
                "transaction_type": "BUY",
                "quantity": 1,
                "price": 1,
                "gross_transaction_amount": 1,
                "trade_currency": "USD",
                "currency": "USD",
            }
        ]
    }
    ingest_response = await async_test_client.post(
        "/ingest/transactions",
        headers={"X-Correlation-Id": "ING:test-correlation-id"},
        json=payload,
    )
    job_id = ingest_response.json()["job_id"]
    ingestion_test_harness["fake_job_service"].fail_mark_queued_job_ids.add(job_id)

    first = await event_replay_test_client.post(
        "/ingestion/dlq/consumer-events/cdlq_test_001/replay",
        json={"dry_run": False},
    )
    assert first.status_code == 500
    first_body = first.json()
    assert first_body["detail"]["code"] == "INGESTION_DLQ_REPLAY_BOOKKEEPING_FAILED"
    assert first_body["detail"]["replay_audit_id"]
    assert first_body["detail"]["replay_fingerprint"]

    audit_response = await event_replay_test_client.get(
        "/ingestion/audit/replays",
        params={"job_id": job_id},
    )
    audits = audit_response.json()["audits"]
    assert any(row["replay_status"] == "replayed_bookkeeping_failed" for row in audits)

    ingestion_test_harness["fake_job_service"].fail_mark_queued_job_ids.discard(job_id)
    second = await event_replay_test_client.post(
        "/ingestion/dlq/consumer-events/cdlq_test_001/replay",
        json={"dry_run": False},
    )
    assert second.status_code == 200
    assert second.json()["replay_status"] == "duplicate_blocked"


async def test_ingestion_replay_audit_list_and_get(
    async_test_client: httpx.AsyncClient,
    event_replay_test_client: httpx.AsyncClient,
):
    payload = {
        "transactions": [
            {
                "transaction_id": "TX_REPLAY_AUDIT_001",
                "portfolio_id": "P1",
                "instrument_id": "I1",
                "security_id": "S1",
                "transaction_date": "2025-08-12T10:00:00Z",
                "transaction_type": "BUY",
                "quantity": 1,
                "price": 1,
                "gross_transaction_amount": 1,
                "trade_currency": "USD",
                "currency": "USD",
            }
        ]
    }
    await async_test_client.post(
        "/ingest/transactions",
        headers={"X-Correlation-Id": "ING:test-correlation-id"},
        json=payload,
    )
    replay_response = await event_replay_test_client.post(
        "/ingestion/dlq/consumer-events/cdlq_test_001/replay",
        json={"dry_run": True},
    )
    assert replay_response.status_code == 200
    replay_id = replay_response.json()["replay_audit_id"]

    list_response = await event_replay_test_client.get(
        "/ingestion/audit/replays",
        params={"recovery_path": "consumer_dlq_replay"},
    )
    assert list_response.status_code == 200
    audits = list_response.json()["audits"]
    assert any(item["replay_id"] == replay_id for item in audits)

    get_response = await event_replay_test_client.get(f"/ingestion/audit/replays/{replay_id}")
    assert get_response.status_code == 200
    assert get_response.json()["replay_id"] == replay_id


def _build_hs256_jwt(secret: str, payload: dict) -> str:
    header = {"alg": "HS256", "typ": "JWT"}

    def _b64(value: dict) -> str:
        raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    header_b64 = _b64(header)
    payload_b64 = _b64(payload)
    signed = f"{header_b64}.{payload_b64}".encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")
    return f"{header_b64}.{payload_b64}.{signature_b64}"


async def test_ingestion_ops_supports_bearer_jwt(
    event_replay_test_client: httpx.AsyncClient,
    monkeypatch,
):
    now_epoch = int(datetime.now(UTC).timestamp())
    secret = "test-hs256-secret"
    for module in {ops_controls, app_ops_controls}:
        monkeypatch.setattr(module, "OPS_AUTH_MODE", "token_or_jwt")
        monkeypatch.setattr(module, "OPS_JWT_HS256_SECRET", secret)
        monkeypatch.setattr(module, "OPS_JWT_ISSUER", "")
        monkeypatch.setattr(module, "OPS_JWT_AUDIENCE", "")
    payload = {"sub": "ops-jwt-user", "exp": now_epoch + 600}
    token = _build_hs256_jwt(secret, payload)

    response = await event_replay_test_client.get(
        "/ingestion/health/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


async def test_ingest_instruments_endpoint(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    """Tests the POST /ingest/instruments endpoint."""
    mock_kafka_producer.publish_message.reset_mock()
    payload = _instrument_batch_payload("SEC_INST_ACK_001")

    response = await async_test_client.post(
        "/ingest/instruments",
        json=payload,
        headers={"X-Idempotency-Key": "instrument-batch-idem-001"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["message"] == "Instruments accepted for asynchronous ingestion processing."
    assert body["entity_type"] == "instrument"
    assert body["accepted_count"] == 1
    assert body["job_id"]
    assert body["idempotency_key"] == "instrument-batch-idem-001"
    assert body["correlation_id"]
    assert body["request_id"]
    assert body["trace_id"]
    mock_kafka_producer.publish_message.assert_called_once()
    publish_kwargs = mock_kafka_producer.publish_message.call_args.kwargs
    assert publish_kwargs["topic"] == "instruments.received"
    assert publish_kwargs["key"] == "SEC_INST_ACK_001"
    assert publish_kwargs["value"]["security_id"] == "SEC_INST_ACK_001"
    assert dict(publish_kwargs["headers"])["idempotency_key"] == (b"instrument-batch-idem-001")


async def test_ingest_instruments_replays_duplicate_idempotency_key(
    async_test_client: httpx.AsyncClient,
    mock_kafka_producer: MagicMock,
):
    mock_kafka_producer.publish_message.reset_mock()
    payload = _instrument_batch_payload("SEC_INST_IDEM_001")
    headers = {"X-Idempotency-Key": "instrument-replay-001"}

    first = await async_test_client.post("/ingest/instruments", json=payload, headers=headers)
    second = await async_test_client.post("/ingest/instruments", json=payload, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert (
        second.json()["message"] == "Duplicate ingestion request accepted via idempotency replay."
    )
    assert second.json()["job_id"] == first.json()["job_id"]
    assert second.json()["idempotency_key"] == "instrument-replay-001"
    mock_kafka_producer.publish_message.assert_called_once()


async def test_ingest_instruments_returns_503_when_mode_blocks_writes(
    async_test_client: httpx.AsyncClient,
    ingestion_test_harness,
    mock_kafka_producer: MagicMock,
):
    ingestion_test_harness["fake_job_service"].mode = "paused"

    response = await async_test_client.post(
        "/ingest/instruments",
        json=_instrument_batch_payload("SEC_INST_BLOCKED_001"),
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "INGESTION_MODE_BLOCKS_WRITES"
    mock_kafka_producer.publish_message.assert_not_called()


async def test_ingest_instruments_returns_429_when_rate_limited(
    async_test_client: httpx.AsyncClient,
    monkeypatch,
    mock_kafka_producer: MagicMock,
):
    def _raise_rate_limit(*, endpoint: str, record_count: int) -> None:
        raise PermissionError(f"{endpoint} blocked after {record_count} records")

    monkeypatch.setattr(
        instruments_router,
        "enforce_ingestion_write_rate_limit",
        _raise_rate_limit,
    )

    response = await async_test_client.post(
        "/ingest/instruments",
        json=_instrument_batch_payload("SEC_INST_RATE_001", "SEC_INST_RATE_002"),
    )

    assert response.status_code == 429
    assert response.json()["detail"] == {
        "code": "INGESTION_RATE_LIMIT_EXCEEDED",
        "message": "/ingest/instruments blocked after 2 records",
    }
    mock_kafka_producer.publish_message.assert_not_called()


async def test_ingest_instruments_returns_failed_record_keys_when_publish_fails(
    async_test_client: httpx.AsyncClient,
    event_replay_test_client: httpx.AsyncClient,
    mock_kafka_producer: MagicMock,
):
    mock_kafka_producer.publish_message.side_effect = RuntimeError("broker timeout")

    response = await async_test_client.post(
        "/ingest/instruments",
        json=_instrument_batch_payload("SEC_INST_FAIL_001", "SEC_INST_FAIL_002"),
    )

    assert response.status_code == 500
    body = response.json()
    assert body["detail"]["code"] == "INGESTION_PUBLISH_FAILED"
    assert body["detail"]["failed_record_keys"] == ["SEC_INST_FAIL_001", "SEC_INST_FAIL_002"]
    job_id = body["detail"]["job_id"]

    failure_history = await event_replay_test_client.get(f"/ingestion/jobs/{job_id}/failures")
    assert failure_history.status_code == 200
    assert failure_history.json()["failures"][0]["failed_record_keys"] == [
        "SEC_INST_FAIL_001",
        "SEC_INST_FAIL_002",
    ]


async def test_ingest_market_prices_endpoint(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    """Tests the POST /ingest/market-prices endpoint."""
    mock_kafka_producer.publish_message.reset_mock()
    payload = _market_price_batch_payload("SEC_PRICE_ACK_001")

    response = await async_test_client.post(
        "/ingest/market-prices",
        json=payload,
        headers={"X-Idempotency-Key": "market-price-batch-idem-001"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["message"] == "Market prices accepted for asynchronous ingestion processing."
    assert body["entity_type"] == "market_price"
    assert body["accepted_count"] == 1
    assert body["job_id"]
    assert body["idempotency_key"] == "market-price-batch-idem-001"
    assert body["correlation_id"]
    assert body["request_id"]
    assert body["trace_id"]
    mock_kafka_producer.publish_message.assert_called_once()
    publish_kwargs = mock_kafka_producer.publish_message.call_args.kwargs
    assert publish_kwargs["topic"] == "market_prices.raw.received"
    assert publish_kwargs["key"] == "SEC_PRICE_ACK_001"
    assert publish_kwargs["value"]["security_id"] == "SEC_PRICE_ACK_001"
    assert dict(publish_kwargs["headers"])["idempotency_key"] == (b"market-price-batch-idem-001")


async def test_ingest_market_prices_replays_duplicate_idempotency_key(
    async_test_client: httpx.AsyncClient,
    mock_kafka_producer: MagicMock,
):
    mock_kafka_producer.publish_message.reset_mock()
    payload = _market_price_batch_payload("SEC_PRICE_IDEM_001")
    headers = {"X-Idempotency-Key": "market-price-replay-001"}

    first = await async_test_client.post("/ingest/market-prices", json=payload, headers=headers)
    second = await async_test_client.post("/ingest/market-prices", json=payload, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert (
        second.json()["message"] == "Duplicate ingestion request accepted via idempotency replay."
    )
    assert second.json()["job_id"] == first.json()["job_id"]
    assert second.json()["idempotency_key"] == "market-price-replay-001"
    mock_kafka_producer.publish_message.assert_called_once()


async def test_ingest_market_prices_returns_503_when_mode_blocks_writes(
    async_test_client: httpx.AsyncClient,
    ingestion_test_harness,
    mock_kafka_producer: MagicMock,
):
    ingestion_test_harness["fake_job_service"].mode = "paused"

    response = await async_test_client.post(
        "/ingest/market-prices",
        json=_market_price_batch_payload("SEC_PRICE_BLOCKED_001"),
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "INGESTION_MODE_BLOCKS_WRITES"
    mock_kafka_producer.publish_message.assert_not_called()


async def test_ingest_market_prices_returns_429_when_rate_limited(
    async_test_client: httpx.AsyncClient,
    monkeypatch,
    mock_kafka_producer: MagicMock,
):
    def _raise_rate_limit(*, endpoint: str, record_count: int) -> None:
        raise PermissionError(f"{endpoint} blocked after {record_count} records")

    monkeypatch.setattr(
        market_prices_router,
        "enforce_ingestion_write_rate_limit",
        _raise_rate_limit,
    )

    response = await async_test_client.post(
        "/ingest/market-prices",
        json=_market_price_batch_payload("SEC_PRICE_RATE_001", "SEC_PRICE_RATE_002"),
    )

    assert response.status_code == 429
    assert response.json()["detail"] == {
        "code": "INGESTION_RATE_LIMIT_EXCEEDED",
        "message": "/ingest/market-prices blocked after 2 records",
    }
    mock_kafka_producer.publish_message.assert_not_called()


async def test_ingest_market_prices_returns_failed_record_keys_when_publish_fails(
    async_test_client: httpx.AsyncClient,
    event_replay_test_client: httpx.AsyncClient,
    mock_kafka_producer: MagicMock,
):
    mock_kafka_producer.publish_message.side_effect = RuntimeError("broker timeout")

    response = await async_test_client.post(
        "/ingest/market-prices",
        json=_market_price_batch_payload("SEC_PRICE_FAIL_001", "SEC_PRICE_FAIL_002"),
    )

    assert response.status_code == 500
    body = response.json()
    assert body["detail"]["code"] == "INGESTION_PUBLISH_FAILED"
    assert body["detail"]["failed_record_keys"] == ["SEC_PRICE_FAIL_001", "SEC_PRICE_FAIL_002"]
    job_id = body["detail"]["job_id"]

    failure_history = await event_replay_test_client.get(f"/ingestion/jobs/{job_id}/failures")
    assert failure_history.status_code == 200
    assert failure_history.json()["failures"][0]["failed_record_keys"] == [
        "SEC_PRICE_FAIL_001",
        "SEC_PRICE_FAIL_002",
    ]


async def test_ingest_fx_rates_endpoint(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    """Tests the POST /ingest/fx-rates endpoint."""
    mock_kafka_producer.publish_message.reset_mock()
    payload = _fx_rate_batch_payload(("USD", "SGD"))

    response = await async_test_client.post(
        "/ingest/fx-rates",
        json=payload,
        headers={"X-Idempotency-Key": "fx-rate-batch-idem-001"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["message"] == "FX rates accepted for asynchronous ingestion processing."
    assert body["entity_type"] == "fx_rate"
    assert body["accepted_count"] == 1
    assert body["job_id"]
    assert body["idempotency_key"] == "fx-rate-batch-idem-001"
    assert body["correlation_id"]
    assert body["request_id"]
    assert body["trace_id"]
    mock_kafka_producer.publish_message.assert_called_once()
    publish_kwargs = mock_kafka_producer.publish_message.call_args.kwargs
    assert publish_kwargs["topic"] == "fx_rates.raw.received"
    assert publish_kwargs["key"] == "USD-SGD-2025-01-01"
    assert publish_kwargs["value"]["from_currency"] == "USD"
    assert publish_kwargs["value"]["to_currency"] == "SGD"
    assert dict(publish_kwargs["headers"])["idempotency_key"] == b"fx-rate-batch-idem-001"


async def test_ingest_fx_rates_replays_duplicate_idempotency_key(
    async_test_client: httpx.AsyncClient,
    mock_kafka_producer: MagicMock,
):
    mock_kafka_producer.publish_message.reset_mock()
    payload = _fx_rate_batch_payload(("USD", "CHF"))
    headers = {"X-Idempotency-Key": "fx-rate-replay-001"}

    first = await async_test_client.post("/ingest/fx-rates", json=payload, headers=headers)
    second = await async_test_client.post("/ingest/fx-rates", json=payload, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert (
        second.json()["message"] == "Duplicate ingestion request accepted via idempotency replay."
    )
    assert second.json()["job_id"] == first.json()["job_id"]
    assert second.json()["idempotency_key"] == "fx-rate-replay-001"
    mock_kafka_producer.publish_message.assert_called_once()


async def test_ingest_fx_rates_returns_503_when_mode_blocks_writes(
    async_test_client: httpx.AsyncClient,
    ingestion_test_harness,
    mock_kafka_producer: MagicMock,
):
    ingestion_test_harness["fake_job_service"].mode = "paused"

    response = await async_test_client.post(
        "/ingest/fx-rates",
        json=_fx_rate_batch_payload(("USD", "JPY")),
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "INGESTION_MODE_BLOCKS_WRITES"
    mock_kafka_producer.publish_message.assert_not_called()


async def test_ingest_fx_rates_returns_429_when_rate_limited(
    async_test_client: httpx.AsyncClient,
    monkeypatch,
    mock_kafka_producer: MagicMock,
):
    def _raise_rate_limit(*, endpoint: str, record_count: int) -> None:
        raise PermissionError(f"{endpoint} blocked after {record_count} records")

    monkeypatch.setattr(
        fx_rates_router,
        "enforce_ingestion_write_rate_limit",
        _raise_rate_limit,
    )

    response = await async_test_client.post(
        "/ingest/fx-rates",
        json=_fx_rate_batch_payload(("USD", "SGD"), ("USD", "EUR")),
    )

    assert response.status_code == 429
    assert response.json()["detail"] == {
        "code": "INGESTION_RATE_LIMIT_EXCEEDED",
        "message": "/ingest/fx-rates blocked after 2 records",
    }
    mock_kafka_producer.publish_message.assert_not_called()


async def test_ingest_fx_rates_returns_failed_record_keys_when_publish_fails(
    async_test_client: httpx.AsyncClient,
    event_replay_test_client: httpx.AsyncClient,
    mock_kafka_producer: MagicMock,
):
    mock_kafka_producer.publish_message.side_effect = RuntimeError("broker timeout")

    response = await async_test_client.post(
        "/ingest/fx-rates",
        json=_fx_rate_batch_payload(("USD", "SGD"), ("EUR", "USD")),
    )

    assert response.status_code == 500
    body = response.json()
    assert body["detail"]["code"] == "INGESTION_PUBLISH_FAILED"
    assert body["detail"]["failed_record_keys"] == [
        "USD-SGD-2025-01-01",
        "EUR-USD-2025-01-01",
    ]
    job_id = body["detail"]["job_id"]

    failure_history = await event_replay_test_client.get(f"/ingestion/jobs/{job_id}/failures")
    assert failure_history.status_code == 200
    assert failure_history.json()["failures"][0]["failed_record_keys"] == [
        "USD-SGD-2025-01-01",
        "EUR-USD-2025-01-01",
    ]


async def test_ingest_cash_account_masters_endpoint(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    mock_kafka_producer.publish_message.reset_mock()
    payload = {
        "cash_accounts": [
            {
                "cash_account_id": "CASH-ACC-USD-001",
                "portfolio_id": "P1",
                "security_id": "CASH_USD",
                "display_name": "USD Operating Cash",
                "account_currency": "USD",
                "lifecycle_status": "ACTIVE",
            }
        ]
    }

    response = await async_test_client.post("/ingest/reference/cash-accounts", json=payload)

    assert response.status_code == 202
    mock_kafka_producer.publish_message.assert_not_called()


async def test_ingest_instrument_lookthrough_components_endpoint(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    mock_kafka_producer.publish_message.reset_mock()
    payload = {
        "lookthrough_components": [
            {
                "parent_security_id": "FUND_001",
                "component_security_id": "ETF_001",
                "effective_from": "2026-01-01",
                "component_weight": "0.6000000000",
            }
        ]
    }

    response = await async_test_client.post(
        "/ingest/reference/instrument-lookthrough-components",
        json=payload,
    )

    assert response.status_code == 202
    mock_kafka_producer.publish_message.assert_not_called()


async def test_ingest_portfolio_bundle_endpoint(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    """Tests the POST /ingest/portfolio-bundle endpoint."""
    mock_kafka_producer.publish_message.reset_mock()
    payload = _portfolio_bundle_payload()

    response = await async_test_client.post(
        "/ingest/portfolio-bundle",
        json=payload,
        headers={"X-Idempotency-Key": "portfolio-bundle-idem-001"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["entity_type"] == "portfolio_bundle"
    assert body["accepted_count"] == 6
    assert body["job_id"]
    assert body["idempotency_key"] == "portfolio-bundle-idem-001"
    assert body["correlation_id"]
    assert body["request_id"]
    assert body["trace_id"]
    assert "Published counts:" in body["message"]
    assert mock_kafka_producer.publish_message.call_count == 6
    published_topics = [
        call.kwargs["topic"] for call in mock_kafka_producer.publish_message.call_args_list
    ]
    assert published_topics == [
        "business_dates.raw.received",
        "portfolios.raw.received",
        "instruments.received",
        "transactions.raw.received",
        "market_prices.raw.received",
        "fx_rates.raw.received",
    ]
    assert (
        dict(mock_kafka_producer.publish_message.call_args_list[0].kwargs["headers"])[
            "idempotency_key"
        ]
        == b"portfolio-bundle-idem-001"
    )


async def test_ingest_portfolio_bundle_replays_duplicate_idempotency_key(
    async_test_client: httpx.AsyncClient,
    mock_kafka_producer: MagicMock,
):
    mock_kafka_producer.publish_message.reset_mock()
    payload = _portfolio_bundle_payload()
    headers = {"X-Idempotency-Key": "portfolio-bundle-replay-001"}

    first = await async_test_client.post("/ingest/portfolio-bundle", json=payload, headers=headers)
    second = await async_test_client.post("/ingest/portfolio-bundle", json=payload, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert (
        second.json()["message"] == "Duplicate ingestion request accepted via idempotency replay."
    )
    assert second.json()["job_id"] == first.json()["job_id"]
    assert second.json()["idempotency_key"] == "portfolio-bundle-replay-001"
    assert mock_kafka_producer.publish_message.call_count == 6


async def test_ingest_portfolio_bundle_rejects_empty_payload(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    response = await async_test_client.post("/ingest/portfolio-bundle", json={})

    assert response.status_code == 422
    assert "at least one non-empty entity list" in response.text
    mock_kafka_producer.publish_message.assert_not_called()


async def test_ingest_portfolio_bundle_rejects_metadata_only_payload(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    payload = {
        "source_system": "UI_UPLOAD",
        "mode": "UPSERT",
    }

    response = await async_test_client.post("/ingest/portfolio-bundle", json=payload)

    assert response.status_code == 422
    assert "at least one non-empty entity list" in response.text
    mock_kafka_producer.publish_message.assert_not_called()


async def test_ingest_portfolio_bundle_disabled_by_feature_flag(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock, monkeypatch
):
    monkeypatch.setenv("LOTUS_CORE_INGEST_PORTFOLIO_BUNDLE_ENABLED", "false")
    payload = {
        "source_system": "UI_UPLOAD",
        "mode": "UPSERT",
        "business_dates": [{"business_date": "2026-01-02"}],
    }
    response = await async_test_client.post("/ingest/portfolio-bundle", json=payload)

    assert response.status_code == 410
    body = response.json()
    assert body["detail"]["code"] == "LOTUS_CORE_ADAPTER_MODE_DISABLED"
    assert body["detail"]["capability"] == "lotus_core.ingestion.portfolio_bundle_adapter"
    mock_kafka_producer.publish_message.assert_not_called()


async def test_ingest_portfolio_bundle_returns_503_when_mode_blocks_writes(
    async_test_client: httpx.AsyncClient,
    ingestion_test_harness,
    mock_kafka_producer: MagicMock,
):
    ingestion_test_harness["fake_job_service"].mode = "paused"

    response = await async_test_client.post(
        "/ingest/portfolio-bundle",
        json=_portfolio_bundle_payload(),
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "INGESTION_MODE_BLOCKS_WRITES"
    mock_kafka_producer.publish_message.assert_not_called()


async def test_ingest_portfolio_bundle_returns_429_when_rate_limited(
    async_test_client: httpx.AsyncClient,
    monkeypatch,
    mock_kafka_producer: MagicMock,
):
    def _raise_rate_limit(*, endpoint: str, record_count: int) -> None:
        raise PermissionError(f"{endpoint} blocked after {record_count} records")

    monkeypatch.setattr(
        portfolio_bundle_router,
        "enforce_ingestion_write_rate_limit",
        _raise_rate_limit,
    )

    response = await async_test_client.post(
        "/ingest/portfolio-bundle",
        json=_portfolio_bundle_payload(),
    )

    assert response.status_code == 429
    assert response.json()["detail"] == {
        "code": "INGESTION_RATE_LIMIT_EXCEEDED",
        "message": "/ingest/portfolio-bundle blocked after 6 records",
    }
    mock_kafka_producer.publish_message.assert_not_called()


async def test_ingest_portfolio_bundle_returns_failed_record_keys_when_publish_fails(
    async_test_client: httpx.AsyncClient,
    event_replay_test_client: httpx.AsyncClient,
    mock_kafka_producer: MagicMock,
):
    mock_kafka_producer.publish_message.side_effect = [None, RuntimeError("broker timeout")]

    response = await async_test_client.post(
        "/ingest/portfolio-bundle",
        json=_portfolio_bundle_payload(),
    )

    assert response.status_code == 500
    body = response.json()
    assert body["detail"]["code"] == "INGESTION_PUBLISH_FAILED"
    assert body["detail"]["failed_record_keys"] == ["P1"]
    assert "'business_dates': 1" in body["detail"]["message"]
    assert "'portfolios': 0" in body["detail"]["message"]
    job_id = body["detail"]["job_id"]

    failure_history = await event_replay_test_client.get(f"/ingestion/jobs/{job_id}/failures")
    assert failure_history.status_code == 200
    assert failure_history.json()["failures"][0]["failed_record_keys"] == ["P1"]


def _xlsx_upload_bytes(headers: list[str], rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(headers)
    for row in rows:
        worksheet.append(row)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


async def test_upload_preview_transactions_csv(async_test_client: httpx.AsyncClient):
    csv_content = "\n".join(
        [
            "transaction_id,portfolio_id,instrument_id,security_id,transaction_date,transaction_type,quantity,price,gross_transaction_amount,trade_currency,currency",
            "T1,P1,I1,S1,2026-01-02T10:00:00Z,BUY,10,100,1000,USD,USD",
            "T2,P1,I1,S1,INVALID_DATE,BUY,10,100,1000,USD,USD",
        ]
    ).encode("utf-8")

    response = await async_test_client.post(
        "/ingest/uploads/preview",
        files={"file": ("transactions.csv", csv_content, "text/csv")},
        data={"entity_type": "transactions", "sample_size": "10"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["entity_type"] == "transactions"
    assert body["total_rows"] == 2
    assert body["valid_rows"] == 1
    assert body["invalid_rows"] == 1


async def test_upload_preview_disabled_by_feature_flag(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock, monkeypatch
):
    monkeypatch.setenv("LOTUS_CORE_INGEST_UPLOAD_APIS_ENABLED", "false")
    csv_content = b"transaction_id,portfolio_id\nT1,P1"

    response = await async_test_client.post(
        "/ingest/uploads/preview",
        files={"file": ("transactions.csv", csv_content, "text/csv")},
        data={"entity_type": "transactions", "sample_size": "10"},
    )

    assert response.status_code == 410
    body = response.json()
    assert body["detail"]["code"] == "LOTUS_CORE_ADAPTER_MODE_DISABLED"
    assert body["detail"]["capability"] == "lotus_core.ingestion.bulk_upload_adapter"
    mock_kafka_producer.publish_message.assert_not_called()


async def test_upload_commit_transactions_csv_partial(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    mock_kafka_producer.publish_message.reset_mock()
    csv_content = "\n".join(
        [
            "transaction_id,portfolio_id,instrument_id,security_id,transaction_date,transaction_type,quantity,price,gross_transaction_amount,trade_currency,currency",
            "T1,P1,I1,S1,2026-01-02T10:00:00Z,BUY,10,100,1000,USD,USD",
            "T2,P1,I1,S1,INVALID_DATE,BUY,10,100,1000,USD,USD",
        ]
    ).encode("utf-8")

    response = await async_test_client.post(
        "/ingest/uploads/commit",
        files={"file": ("transactions.csv", csv_content, "text/csv")},
        data={"entity_type": "transactions", "allow_partial": "true"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["published_rows"] == 1
    assert body["skipped_rows"] == 1
    mock_kafka_producer.publish_message.assert_called_once()


async def test_upload_commit_disabled_by_feature_flag(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock, monkeypatch
):
    monkeypatch.setenv("LOTUS_CORE_INGEST_UPLOAD_APIS_ENABLED", "false")
    csv_content = b"transaction_id,portfolio_id\nT1,P1"
    response = await async_test_client.post(
        "/ingest/uploads/commit",
        files={"file": ("transactions.csv", csv_content, "text/csv")},
        data={"entity_type": "transactions", "allow_partial": "true"},
    )

    assert response.status_code == 410
    body = response.json()
    assert body["detail"]["code"] == "LOTUS_CORE_ADAPTER_MODE_DISABLED"
    assert body["detail"]["capability"] == "lotus_core.ingestion.bulk_upload_adapter"
    mock_kafka_producer.publish_message.assert_not_called()


async def test_upload_commit_xlsx_rejects_invalid_without_partial(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    mock_kafka_producer.publish_message.reset_mock()
    xlsx_content = _xlsx_upload_bytes(
        headers=["security_id", "name", "isin", "currency", "product_type"],
        rows=[
            ["SEC1", "Bond A", "ISIN1", "USD", "Bond"],
            ["SEC2", "", "ISIN2", "USD", "Bond"],
        ],
    )

    response = await async_test_client.post(
        "/ingest/uploads/commit",
        files={
            "file": (
                "instruments.xlsx",
                xlsx_content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        data={"entity_type": "instruments"},
    )

    assert response.status_code == 422
    mock_kafka_producer.publish_message.assert_not_called()


async def test_upload_preview_rejects_malformed_xlsx(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    mock_kafka_producer.publish_message.reset_mock()
    fake_xlsx = b"not-a-real-xlsx"

    response = await async_test_client.post(
        "/ingest/uploads/preview",
        files={
            "file": (
                "fake.xlsx",
                fake_xlsx,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        data={"entity_type": "instruments", "sample_size": "10"},
    )

    assert response.status_code == 400
    assert "Invalid XLSX content" in response.text
    mock_kafka_producer.publish_message.assert_not_called()


async def test_upload_preview_rejects_bad_encoding_csv(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    mock_kafka_producer.publish_message.reset_mock()
    bad_csv = b"transaction_id,portfolio_id\n\xff\xfe\xfd,PORT1"

    response = await async_test_client.post(
        "/ingest/uploads/preview",
        files={"file": ("bad-encoding.csv", bad_csv, "text/csv")},
        data={"entity_type": "transactions", "sample_size": "10"},
    )

    assert response.status_code == 400
    assert "Invalid CSV content" in response.text
    mock_kafka_producer.publish_message.assert_not_called()


async def test_upload_commit_rejects_malformed_xlsx(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    mock_kafka_producer.publish_message.reset_mock()
    fake_xlsx = b"not-a-real-xlsx"

    response = await async_test_client.post(
        "/ingest/uploads/commit",
        files={
            "file": (
                "fake.xlsx",
                fake_xlsx,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        data={"entity_type": "instruments", "allow_partial": "false"},
    )

    assert response.status_code == 400
    assert "Invalid XLSX content" in response.text
    mock_kafka_producer.publish_message.assert_not_called()


async def test_upload_commit_rejects_bad_encoding_csv(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    mock_kafka_producer.publish_message.reset_mock()
    bad_csv = b"transaction_id,portfolio_id\n\xff\xfe\xfd,PORT1"

    response = await async_test_client.post(
        "/ingest/uploads/commit",
        files={"file": ("bad-encoding.csv", bad_csv, "text/csv")},
        data={"entity_type": "transactions", "allow_partial": "false"},
    )

    assert response.status_code == 400
    assert "Invalid CSV content" in response.text
    mock_kafka_producer.publish_message.assert_not_called()


async def test_reprocess_transactions_rejects_empty_transaction_ids(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    mock_kafka_producer.publish_message.reset_mock()

    response = await async_test_client.post(
        "/reprocess/transactions",
        json={"transaction_ids": []},
    )

    assert response.status_code == 422
    mock_kafka_producer.publish_message.assert_not_called()


async def test_reprocess_transactions_deduplicates_transaction_ids_at_ingress(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    mock_kafka_producer.publish_message.reset_mock()

    response = await async_test_client.post(
        "/reprocess/transactions",
        json={"transaction_ids": ["TXN1", "TXN2", "TXN1", "TXN2"]},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["message"] == "Successfully queued 2 transactions for reprocessing."
    assert body["entity_type"] == "reprocessing_request"
    assert body["accepted_count"] == 2
    assert body["job_id"]
    assert body["correlation_id"]
    assert body["request_id"]
    assert body["trace_id"]

    published_ids = [
        call.kwargs["value"]["transaction_id"]
        for call in mock_kafka_producer.publish_message.call_args_list
    ]
    assert published_ids == ["TXN1", "TXN2"]
    publish_kwargs = mock_kafka_producer.publish_message.call_args_list[0].kwargs
    assert publish_kwargs["topic"] == "transactions.reprocessing.requested"
    assert publish_kwargs["key"] == "TXN1"


async def test_reprocess_transactions_replays_duplicate_idempotency_key(
    async_test_client: httpx.AsyncClient,
    mock_kafka_producer: MagicMock,
):
    mock_kafka_producer.publish_message.reset_mock()
    payload = {"transaction_ids": ["TXN_IDEM_001", "TXN_IDEM_002"]}
    headers = {"X-Idempotency-Key": "reprocessing-replay-001"}

    first = await async_test_client.post("/reprocess/transactions", json=payload, headers=headers)
    second = await async_test_client.post("/reprocess/transactions", json=payload, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert (
        second.json()["message"]
        == "Duplicate reprocessing request accepted via idempotency replay."
    )
    assert second.json()["job_id"] == first.json()["job_id"]
    assert second.json()["idempotency_key"] == "reprocessing-replay-001"
    assert mock_kafka_producer.publish_message.call_count == 2


async def test_reprocess_transactions_returns_503_when_mode_blocks_writes(
    async_test_client: httpx.AsyncClient,
    ingestion_test_harness,
    mock_kafka_producer: MagicMock,
):
    ingestion_test_harness["fake_job_service"].mode = "paused"

    response = await async_test_client.post(
        "/reprocess/transactions",
        json={"transaction_ids": ["TXN_BLOCKED_001"]},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "INGESTION_MODE_BLOCKS_WRITES"
    mock_kafka_producer.publish_message.assert_not_called()


async def test_reprocess_transactions_returns_409_when_reprocessing_policy_blocks_publish(
    async_test_client: httpx.AsyncClient,
    ingestion_test_harness,
    mock_kafka_producer: MagicMock,
):
    ingestion_test_harness["fake_job_service"].reprocessing_publish_allowed = False

    response = await async_test_client.post(
        "/reprocess/transactions",
        json={"transaction_ids": ["TXN_REPLAY_BLOCKED_001", "TXN_REPLAY_BLOCKED_002"]},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "INGESTION_REPLAY_BLOCKED",
        "message": "Reprocessing publication is blocked for 2 record(s).",
    }
    mock_kafka_producer.publish_message.assert_not_called()


async def test_reprocess_transactions_returns_429_when_rate_limited(
    async_test_client: httpx.AsyncClient,
    monkeypatch,
    mock_kafka_producer: MagicMock,
):
    def _raise_rate_limit(*, endpoint: str, record_count: int) -> None:
        raise PermissionError(f"{endpoint} blocked after {record_count} records")

    monkeypatch.setattr(
        reprocessing_router,
        "enforce_ingestion_write_rate_limit",
        _raise_rate_limit,
    )

    response = await async_test_client.post(
        "/reprocess/transactions",
        json={"transaction_ids": ["TXN_RATE_001", "TXN_RATE_002", "TXN_RATE_001"]},
    )

    assert response.status_code == 429
    assert response.json()["detail"] == {
        "code": "INGESTION_RATE_LIMIT_EXCEEDED",
        "message": "/reprocess/transactions blocked after 2 records",
    }
    mock_kafka_producer.publish_message.assert_not_called()


async def test_reprocess_transactions_records_remaining_unpublished_keys_on_partial_failure(
    async_test_client: httpx.AsyncClient,
    event_replay_test_client: httpx.AsyncClient,
    mock_kafka_producer: MagicMock,
):
    mock_kafka_producer.publish_message.side_effect = [None, RuntimeError("broker timeout")]

    response = await async_test_client.post(
        "/reprocess/transactions",
        json={"transaction_ids": ["TXN1", "TXN2", "TXN3"]},
    )

    assert response.status_code == 500
    body = response.json()
    assert body["detail"]["code"] == "INGESTION_PUBLISH_FAILED"
    assert body["detail"]["failed_record_keys"] == ["TXN2", "TXN3"]
    failed_job_id = body["detail"]["job_id"]

    jobs_response = await event_replay_test_client.get(
        "/ingestion/jobs",
        params={"status": "failed"},
    )
    assert jobs_response.status_code == 200
    assert jobs_response.json()["jobs"][0]["job_id"] == failed_job_id

    failure_history = await event_replay_test_client.get(
        f"/ingestion/jobs/{failed_job_id}/failures"
    )
    assert failure_history.status_code == 200
    assert failure_history.json()["failures"][0]["failed_record_keys"] == ["TXN2", "TXN3"]


@pytest.mark.parametrize(
    ("path", "payload", "entity_type"),
    [
        (
            "/ingest/portfolios",
            {
                "portfolios": [
                    {
                        "portfolio_id": "P1",
                        "base_currency": "USD",
                        "open_date": "2025-01-01",
                        "client_id": "c",
                        "status": "s",
                        "risk_exposure": "r",
                        "investment_time_horizon": "i",
                        "portfolio_type": "t",
                        "booking_center_code": "b",
                    }
                ]
            },
            "portfolio",
        ),
        (
            "/ingest/transactions",
            {
                "transactions": [
                    {
                        "transaction_id": "T1",
                        "portfolio_id": "P1",
                        "instrument_id": "I1",
                        "security_id": "S1",
                        "transaction_date": "2025-08-12T10:00:00Z",
                        "transaction_type": "BUY",
                        "quantity": 1,
                        "price": 1,
                        "gross_transaction_amount": 1,
                        "trade_currency": "USD",
                        "currency": "USD",
                    }
                ]
            },
            "transaction",
        ),
        (
            "/ingest/instruments",
            {
                "instruments": [
                    {
                        "security_id": "S1",
                        "name": "N1",
                        "isin": "I1",
                        "currency": "USD",
                        "product_type": "E",
                    }
                ]
            },
            "instrument",
        ),
        (
            "/ingest/market-prices",
            {
                "market_prices": [
                    {
                        "security_id": "S1",
                        "price_date": "2025-01-01",
                        "price": 100,
                        "currency": "USD",
                    }
                ]
            },
            "market_price",
        ),
        (
            "/ingest/fx-rates",
            {
                "fx_rates": [
                    {
                        "from_currency": "USD",
                        "to_currency": "EUR",
                        "rate_date": "2025-01-01",
                        "rate": 0.9,
                    }
                ]
            },
            "fx_rate",
        ),
        (
            "/ingest/business-dates",
            {"business_dates": [{"business_date": "2025-01-01"}]},
            "business_date",
        ),
    ],
)
async def test_ingestion_endpoints_return_canonical_ack_contract(
    async_test_client: httpx.AsyncClient,
    path: str,
    payload: dict,
    entity_type: str,
):
    response = await async_test_client.post(
        path,
        json=payload,
        headers={"X-Idempotency-Key": "integration-ingestion-idempotency-001"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["entity_type"] == entity_type
    assert body["accepted_count"] >= 1
    assert body["idempotency_key"] == "integration-ingestion-idempotency-001"
    assert body["correlation_id"]
    assert body["request_id"]
    assert body["trace_id"]
    assert "job_id" in body


async def test_business_date_ingestion_rejects_future_dates(
    async_test_client: httpx.AsyncClient,
):
    response = await async_test_client.post(
        "/ingest/business-dates",
        json={"business_dates": [{"business_date": "2999-01-01"}]},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["detail"]["code"] == "BUSINESS_DATE_FUTURE_POLICY_VIOLATION"


async def test_ingest_business_dates_endpoint(
    async_test_client: httpx.AsyncClient,
    mock_kafka_producer: MagicMock,
):
    mock_kafka_producer.publish_message.reset_mock()

    response = await async_test_client.post(
        "/ingest/business-dates",
        json=_business_date_batch_payload("2025-01-02"),
        headers={"X-Idempotency-Key": "business-date-batch-idem-001"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["message"] == "Business dates accepted for asynchronous ingestion processing."
    assert body["entity_type"] == "business_date"
    assert body["accepted_count"] == 1
    assert body["job_id"]
    assert body["idempotency_key"] == "business-date-batch-idem-001"
    assert body["correlation_id"]
    assert body["request_id"]
    assert body["trace_id"]
    mock_kafka_producer.publish_message.assert_called_once()
    publish_kwargs = mock_kafka_producer.publish_message.call_args.kwargs
    assert publish_kwargs["topic"] == "business_dates.raw.received"
    assert publish_kwargs["key"] == "GLOBAL|2025-01-02"
    assert publish_kwargs["value"]["business_date"].isoformat() == "2025-01-02"
    assert dict(publish_kwargs["headers"])["idempotency_key"] == (b"business-date-batch-idem-001")


async def test_ingest_business_dates_replays_duplicate_idempotency_key(
    async_test_client: httpx.AsyncClient,
    mock_kafka_producer: MagicMock,
):
    mock_kafka_producer.publish_message.reset_mock()
    payload = _business_date_batch_payload("2025-01-03")
    headers = {"X-Idempotency-Key": "business-date-replay-001"}

    first = await async_test_client.post("/ingest/business-dates", json=payload, headers=headers)
    second = await async_test_client.post("/ingest/business-dates", json=payload, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert (
        second.json()["message"] == "Duplicate ingestion request accepted via idempotency replay."
    )
    assert second.json()["job_id"] == first.json()["job_id"]
    assert second.json()["idempotency_key"] == "business-date-replay-001"
    mock_kafka_producer.publish_message.assert_called_once()


async def test_ingest_business_dates_rejects_empty_payload_with_canonical_error(
    async_test_client: httpx.AsyncClient,
    mock_kafka_producer: MagicMock,
):
    response = await async_test_client.post(
        "/ingest/business-dates",
        json={"business_dates": []},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "BUSINESS_DATE_PAYLOAD_EMPTY",
        "message": "At least one business_date record is required.",
    }
    mock_kafka_producer.publish_message.assert_not_called()


async def test_ingest_business_dates_returns_503_when_mode_blocks_writes(
    async_test_client: httpx.AsyncClient,
    ingestion_test_harness,
    mock_kafka_producer: MagicMock,
):
    ingestion_test_harness["fake_job_service"].mode = "paused"

    response = await async_test_client.post(
        "/ingest/business-dates",
        json=_business_date_batch_payload("2025-01-04"),
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "INGESTION_MODE_BLOCKS_WRITES"
    mock_kafka_producer.publish_message.assert_not_called()


async def test_ingest_business_dates_returns_429_when_rate_limited(
    async_test_client: httpx.AsyncClient,
    monkeypatch,
    mock_kafka_producer: MagicMock,
):
    def _raise_rate_limit(*, endpoint: str, record_count: int) -> None:
        raise PermissionError(f"{endpoint} blocked after {record_count} records")

    monkeypatch.setattr(
        business_dates_router,
        "enforce_ingestion_write_rate_limit",
        _raise_rate_limit,
    )

    response = await async_test_client.post(
        "/ingest/business-dates",
        json=_business_date_batch_payload("2025-01-05", "2025-01-06"),
    )

    assert response.status_code == 429
    assert response.json()["detail"] == {
        "code": "INGESTION_RATE_LIMIT_EXCEEDED",
        "message": "/ingest/business-dates blocked after 2 records",
    }
    mock_kafka_producer.publish_message.assert_not_called()


async def test_ingest_business_dates_rejects_monotonic_regression(
    async_test_client: httpx.AsyncClient,
    ingestion_test_harness,
    monkeypatch,
    mock_kafka_producer: MagicMock,
):
    monkeypatch.setattr(business_dates_router, "BUSINESS_DATE_ENFORCE_MONOTONIC_ADVANCE", True)
    ingestion_test_harness["fake_business_calendar_repository"].latest_business_dates["GLOBAL"] = (
        datetime(2025, 1, 10).date()
    )

    response = await async_test_client.post(
        "/ingest/business-dates",
        json=_business_date_batch_payload("2025-01-09"),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "BUSINESS_DATE_MONOTONIC_POLICY_VIOLATION"
    assert "latest persisted '2025-01-10'" in response.json()["detail"]["message"]
    mock_kafka_producer.publish_message.assert_not_called()


async def test_ingest_business_dates_returns_failed_record_keys_when_publish_fails(
    async_test_client: httpx.AsyncClient,
    event_replay_test_client: httpx.AsyncClient,
    mock_kafka_producer: MagicMock,
):
    mock_kafka_producer.publish_message.side_effect = RuntimeError("broker timeout")

    response = await async_test_client.post(
        "/ingest/business-dates",
        json=_business_date_batch_payload("2025-01-07", "2025-01-08"),
    )

    assert response.status_code == 500
    body = response.json()
    assert body["detail"]["code"] == "INGESTION_PUBLISH_FAILED"
    assert body["detail"]["failed_record_keys"] == [
        "GLOBAL|2025-01-07",
        "GLOBAL|2025-01-08",
    ]
    job_id = body["detail"]["job_id"]

    failure_history = await event_replay_test_client.get(f"/ingestion/jobs/{job_id}/failures")
    assert failure_history.status_code == 200
    assert failure_history.json()["failures"][0]["failed_record_keys"] == [
        "GLOBAL|2025-01-07",
        "GLOBAL|2025-01-08",
    ]


async def test_transaction_ingestion_allows_future_dated_trade(
    async_test_client: httpx.AsyncClient,
):
    response = await async_test_client.post(
        "/ingest/transactions",
        json={
            "transactions": [
                {
                    "transaction_id": "TXN_FUTURE_ALLOWED_001",
                    "portfolio_id": "P1",
                    "instrument_id": "I1",
                    "security_id": "S1",
                    "transaction_date": "2999-01-01T00:00:00Z",
                    "transaction_type": "BUY",
                    "quantity": 10,
                    "price": 100,
                    "gross_transaction_amount": 1000,
                    "trade_currency": "USD",
                    "currency": "USD",
                }
            ]
        },
    )
    assert response.status_code == 202


@pytest.mark.parametrize(
    ("path", "payload", "entity_type"),
    [
        (
            "/ingest/benchmark-assignments",
            {
                "benchmark_assignments": [
                    {
                        "portfolio_id": "P1",
                        "benchmark_id": "BMK_001",
                        "effective_from": "2026-01-01",
                        "assignment_version": 1,
                        "assignment_source": "benchmark_policy_engine",
                        "assignment_status": "active",
                    }
                ]
            },
            "benchmark_assignment",
        ),
        (
            "/ingest/benchmark-definitions",
            {
                "benchmark_definitions": [
                    {
                        "benchmark_id": "BMK_001",
                        "effective_from": "2026-01-01",
                        "benchmark_name": "Balanced Mandate Benchmark",
                        "benchmark_type": "composite",
                        "benchmark_currency": "USD",
                        "return_convention": "total_return_index",
                        "benchmark_status": "active",
                    }
                ]
            },
            "benchmark_definition",
        ),
        (
            "/ingest/benchmark-compositions",
            {
                "benchmark_compositions": [
                    {
                        "benchmark_id": "BMK_001",
                        "index_id": "IDX_001",
                        "composition_effective_from": "2026-01-01",
                        "composition_weight": "1.0",
                    }
                ]
            },
            "benchmark_composition",
        ),
        (
            "/ingest/indices",
            {
                "indices": [
                    {
                        "index_id": "IDX_001",
                        "effective_from": "2026-01-01",
                        "index_name": "MSCI World",
                        "index_currency": "USD",
                        "index_type": "equity",
                        "index_status": "active",
                    }
                ]
            },
            "index_definition",
        ),
        (
            "/ingest/index-price-series",
            {
                "index_price_series": [
                    {
                        "series_id": "IDXP_001",
                        "index_id": "IDX_001",
                        "series_date": "2026-01-01",
                        "index_price": "1234.56",
                        "series_currency": "USD",
                        "value_convention": "close",
                    }
                ]
            },
            "index_price_series",
        ),
        (
            "/ingest/index-return-series",
            {
                "index_return_series": [
                    {
                        "series_id": "IDXR_001",
                        "index_id": "IDX_001",
                        "series_date": "2026-01-01",
                        "index_return": "0.0123",
                        "return_period": "daily",
                        "return_convention": "gross",
                        "series_currency": "USD",
                    }
                ]
            },
            "index_return_series",
        ),
        (
            "/ingest/benchmark-return-series",
            {
                "benchmark_return_series": [
                    {
                        "series_id": "BMKR_001",
                        "benchmark_id": "BMK_001",
                        "series_date": "2026-01-01",
                        "benchmark_return": "0.0100",
                        "return_period": "daily",
                        "return_convention": "gross",
                        "series_currency": "USD",
                    }
                ]
            },
            "benchmark_return_series",
        ),
        (
            "/ingest/risk-free-series",
            {
                "risk_free_series": [
                    {
                        "series_id": "RF_001",
                        "risk_free_curve_id": "USD_OIS",
                        "series_date": "2026-01-01",
                        "value": "0.035",
                        "value_convention": "annualized_rate",
                        "day_count_convention": "ACT_360",
                        "compounding_convention": "simple",
                        "series_currency": "USD",
                    }
                ]
            },
            "risk_free_series",
        ),
        (
            "/ingest/reference/classification-taxonomy",
            {
                "classification_taxonomy": [
                    {
                        "classification_set_id": "TAX_001",
                        "taxonomy_scope": "portfolio_workspace",
                        "dimension_name": "asset_class",
                        "dimension_value": "EQUITY",
                        "effective_from": "2026-01-01",
                    }
                ]
            },
            "classification_taxonomy",
        ),
        (
            "/ingest/reference/cash-accounts",
            {
                "cash_accounts": [
                    {
                        "cash_account_id": "CASH-ACC-USD-001",
                        "portfolio_id": "P1",
                        "security_id": "CASH_USD",
                        "display_name": "USD Operating Cash",
                        "account_currency": "USD",
                        "lifecycle_status": "ACTIVE",
                    }
                ]
            },
            "cash_account_master",
        ),
        (
            "/ingest/reference/instrument-lookthrough-components",
            {
                "lookthrough_components": [
                    {
                        "parent_security_id": "FUND_001",
                        "component_security_id": "ETF_001",
                        "effective_from": "2026-01-01",
                        "component_weight": "0.6000000000",
                    }
                ]
            },
            "instrument_lookthrough_component",
        ),
    ],
)
async def test_reference_data_ingestion_endpoints_return_canonical_ack_contract(
    async_test_client: httpx.AsyncClient,
    path: str,
    payload: dict,
    entity_type: str,
):
    response = await async_test_client.post(
        path,
        json=payload,
        headers={"X-Idempotency-Key": f"{entity_type}-idempotency"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["entity_type"] == entity_type
    assert body["accepted_count"] == 1
    assert body["idempotency_key"] == f"{entity_type}-idempotency"
    assert body["job_id"]


async def test_reference_data_ingestion_replays_duplicate_idempotency_key(
    async_test_client: httpx.AsyncClient,
):
    payload = {
        "cash_accounts": [
            {
                "cash_account_id": "CASH-ACC-USD-001",
                "portfolio_id": "P1",
                "security_id": "CASH_USD",
                "display_name": "USD Operating Cash",
                "account_currency": "USD",
                "lifecycle_status": "ACTIVE",
            }
        ]
    }

    first = await async_test_client.post(
        "/ingest/reference/cash-accounts",
        json=payload,
        headers={"X-Idempotency-Key": "cash-account-replay"},
    )
    second = await async_test_client.post(
        "/ingest/reference/cash-accounts",
        json=payload,
        headers={"X-Idempotency-Key": "cash-account-replay"},
    )

    assert first.status_code == 202
    assert second.status_code == 202
    second_body = second.json()
    assert second_body["message"] == "Duplicate ingestion request accepted via idempotency replay."
    assert second_body["job_id"] == first.json()["job_id"]


async def test_reference_data_ingestion_returns_503_when_mode_blocks_writes(
    async_test_client: httpx.AsyncClient,
    ingestion_test_harness,
):
    job_service = ingestion_test_harness["fake_job_service"]
    job_service.mode = "paused"

    response = await async_test_client.post(
        "/ingest/reference/cash-accounts",
        json={
            "cash_accounts": [
                {
                    "cash_account_id": "CASH-ACC-USD-001",
                    "portfolio_id": "P1",
                    "security_id": "CASH_USD",
                    "display_name": "USD Operating Cash",
                    "account_currency": "USD",
                    "lifecycle_status": "ACTIVE",
                }
            ]
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "INGESTION_MODE_BLOCKS_WRITES"


async def test_reference_data_ingestion_returns_429_when_rate_limited(
    async_test_client: httpx.AsyncClient,
    monkeypatch,
):
    def _raise_rate_limit(*, endpoint: str, record_count: int) -> None:
        raise PermissionError(f"{endpoint} blocked after {record_count} records")

    monkeypatch.setattr(
        reference_data_router,
        "enforce_ingestion_write_rate_limit",
        _raise_rate_limit,
    )

    response = await async_test_client.post(
        "/ingest/reference/cash-accounts",
        json={
            "cash_accounts": [
                {
                    "cash_account_id": "CASH-ACC-USD-001",
                    "portfolio_id": "P1",
                    "security_id": "CASH_USD",
                    "display_name": "USD Operating Cash",
                    "account_currency": "USD",
                    "lifecycle_status": "ACTIVE",
                }
            ]
        },
    )

    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "INGESTION_RATE_LIMIT_EXCEEDED"


async def test_reference_data_ingestion_marks_job_failed_when_persist_fn_raises(
    async_test_client: httpx.AsyncClient,
    ingestion_test_harness,
    monkeypatch,
):
    async def _raise_persist_failure(records: list[dict[str, object]]) -> None:
        raise RuntimeError("cash account master persist failed")

    fake_reference_data_service = ingestion_test_harness["fake_reference_data_service"]
    monkeypatch.setattr(
        fake_reference_data_service,
        "upsert_cash_account_masters",
        _raise_persist_failure,
    )

    with pytest.raises(RuntimeError, match="cash account master persist failed"):
        await async_test_client.post(
            "/ingest/reference/cash-accounts",
            json={
                "cash_accounts": [
                    {
                        "cash_account_id": "CASH-ACC-USD-001",
                        "portfolio_id": "P1",
                        "security_id": "CASH_USD",
                        "display_name": "USD Operating Cash",
                        "account_currency": "USD",
                        "lifecycle_status": "ACTIVE",
                    }
                ]
            },
        )

    failed_jobs = [
        job
        for job in ingestion_test_harness["fake_job_service"].jobs.values()
        if job.status == "failed"
    ]
    assert len(failed_jobs) == 1
    assert failed_jobs[0].failure_reason == "cash account master persist failed"
