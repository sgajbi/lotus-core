# tests/integration/services/ingestion-service/test_ingestion_routers.py
from datetime import UTC, datetime
from decimal import Decimal
import base64
import hashlib
import hmac
from io import BytesIO
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
import pytest_asyncio
from openpyxl import Workbook
from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer

from src.services.ingestion_service.app.DTOs.ingestion_job_dto import IngestionJobResponse
from src.services.ingestion_service.app.main import app
from src.services.ingestion_service.app import ops_controls
try:
    from app import ops_controls as app_ops_controls
except ModuleNotFoundError:  # pragma: no cover - only needed in certain test path setups.
    app_ops_controls = ops_controls
from src.services.ingestion_service.app.routers import (
    business_dates as business_dates_router,
)
from src.services.ingestion_service.app.routers import (
    fx_rates as fx_rates_router,
)
from src.services.ingestion_service.app.routers import (
    ingestion_jobs as ingestion_jobs_router,
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
    return mock


@pytest_asyncio.fixture
async def async_test_client(mock_kafka_producer: MagicMock):
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
            self.mode = "normal"
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

        async def mark_retried(self, job_id: str) -> None:
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
                            "Investigate consumer lag and retry this job once root cause is resolved."
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
                    "original_topic": original_topic or "raw_transactions",
                    "consumer_group": consumer_group or "persistence-service-group",
                    "dlq_topic": "persistence_service.dlq",
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
                original_topic="raw_transactions",
                consumer_group="persistence-service-group",
                dlq_topic="persistence_service.dlq",
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
                        "original_topic": "raw_transactions",
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

        async def find_successful_replay_audit_by_fingerprint(
            self,
            replay_fingerprint: str,
            recovery_path: str | None = None,
        ) -> dict[str, str] | None:
            row = self.replay_audit.get(replay_fingerprint)
            if (
                row
                and row.get("replay_status") == "replayed"
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
            return None

    fake_job_service = FakeIngestionJobService()
    app.dependency_overrides[get_ingestion_job_service] = lambda: fake_job_service
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
    app.dependency_overrides[portfolio_bundle_router.get_ingestion_job_service] = lambda: (
        fake_job_service
    )
    app.dependency_overrides[reprocessing_router.get_ingestion_job_service] = lambda: (
        fake_job_service
    )
    app.dependency_overrides[ingestion_jobs_router.get_ingestion_job_service] = lambda: (
        fake_job_service
    )

    app.dependency_overrides[get_kafka_producer] = override_get_kafka_producer

    # --- THIS IS THE FIX ---
    # Use ASGITransport for in-process testing instead of making real network calls.
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Lotus-Ops-Token": "lotus-core-ops-local"},
    ) as client:
        # --- END FIX ---
        yield client

    # Clean up the override after the test
    app.dependency_overrides.pop(get_kafka_producer, None)
    app.dependency_overrides.pop(get_ingestion_job_service, None)
    app.dependency_overrides.pop(transactions_router.get_ingestion_job_service, None)
    app.dependency_overrides.pop(portfolios_router.get_ingestion_job_service, None)
    app.dependency_overrides.pop(instruments_router.get_ingestion_job_service, None)
    app.dependency_overrides.pop(market_prices_router.get_ingestion_job_service, None)
    app.dependency_overrides.pop(fx_rates_router.get_ingestion_job_service, None)
    app.dependency_overrides.pop(business_dates_router.get_ingestion_job_service, None)
    app.dependency_overrides.pop(portfolio_bundle_router.get_ingestion_job_service, None)
    app.dependency_overrides.pop(reprocessing_router.get_ingestion_job_service, None)
    app.dependency_overrides.pop(ingestion_jobs_router.get_ingestion_job_service, None)


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
    mock_kafka_producer.publish_message.assert_called_once()


async def test_ingest_transactions_endpoint(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    """Tests the POST /ingest/transactions endpoint."""
    mock_kafka_producer.publish_message.reset_mock()
    payload = {
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
    }

    response = await async_test_client.post("/ingest/transactions", json=payload)

    assert response.status_code == 202
    body = response.json()
    assert body["entity_type"] == "transaction"
    assert body["accepted_count"] == 1
    assert "job_id" in body
    mock_kafka_producer.publish_message.assert_called_once()


async def test_ingestion_jobs_status_endpoint(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
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

    job_response = await async_test_client.get(f"/ingestion/jobs/{job_id}")
    assert job_response.status_code == 200
    job_body = job_response.json()
    assert job_body["job_id"] == job_id
    assert job_body["status"] == "queued"
    assert job_body["entity_type"] == "transaction"


async def test_ingestion_jobs_list_endpoint(async_test_client: httpx.AsyncClient):
    response = await async_test_client.get("/ingestion/jobs", params={"limit": 5})
    assert response.status_code == 200
    body = response.json()
    assert "jobs" in body
    assert "total" in body
    assert "next_cursor" in body


async def test_ingestion_job_not_found(async_test_client: httpx.AsyncClient):
    response = await async_test_client.get("/ingestion/jobs/job_missing_001")
    assert response.status_code == 404
    body = response.json()
    assert body["detail"]["code"] == "INGESTION_JOB_NOT_FOUND"


async def test_ingestion_jobs_idempotency_replays_existing_job(
    async_test_client: httpx.AsyncClient,
):
    payload = {
        "transactions": [
            {
                "transaction_id": "TX_IDEMPOTENT_001",
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
    headers = {"X-Idempotency-Key": "idem-batch-001"}

    first = await async_test_client.post("/ingest/transactions", json=payload, headers=headers)
    second = await async_test_client.post("/ingest/transactions", json=payload, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]


async def test_ingestion_job_failure_history_and_retry(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    mock_kafka_producer.publish_message.side_effect = RuntimeError("broker timeout")
    payload = {
        "transactions": [
            {
                "transaction_id": "TX_FAIL_001",
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

    jobs_response = await async_test_client.get("/ingestion/jobs", params={"status": "failed"})
    assert jobs_response.status_code == 200
    failed_job_id = jobs_response.json()["jobs"][0]["job_id"]

    failure_history = await async_test_client.get(f"/ingestion/jobs/{failed_job_id}/failures")
    assert failure_history.status_code == 200
    assert failure_history.json()["total"] >= 1

    mock_kafka_producer.publish_message.side_effect = None
    retry_response = await async_test_client.post(f"/ingestion/jobs/{failed_job_id}/retry")
    assert retry_response.status_code == 200
    assert retry_response.json()["status"] == "queued"
    assert retry_response.json()["retry_count"] == 1


async def test_ingestion_job_partial_retry_dry_run(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
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

    dry_run = await async_test_client.post(
        f"/ingestion/jobs/{job_id}/retry",
        json={"record_keys": ["TX_PARTIAL_002"], "dry_run": True},
    )
    assert dry_run.status_code == 200


async def test_ingestion_job_retry_blocks_duplicate_fingerprint(
    async_test_client: httpx.AsyncClient,
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
    first = await async_test_client.post(
        f"/ingestion/jobs/{job_id}/retry",
        json={"dry_run": False},
    )
    assert first.status_code == 200
    second = await async_test_client.post(
        f"/ingestion/jobs/{job_id}/retry",
        json={"dry_run": False},
    )
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "INGESTION_RETRY_DUPLICATE_BLOCKED"


async def test_ingestion_health_summary(async_test_client: httpx.AsyncClient):
    response = await async_test_client.get("/ingestion/health/summary")
    assert response.status_code == 200
    body = response.json()
    assert "total_jobs" in body
    assert "backlog_jobs" in body


async def test_ingestion_slo_status(async_test_client: httpx.AsyncClient):
    response = await async_test_client.get("/ingestion/health/slo")
    assert response.status_code == 200
    body = response.json()
    assert "failure_rate" in body
    assert "p95_queue_latency_seconds" in body


async def test_ingestion_backlog_breakdown(async_test_client: httpx.AsyncClient):
    response = await async_test_client.get("/ingestion/health/backlog-breakdown")
    assert response.status_code == 200
    body = response.json()
    assert "groups" in body
    assert "total_backlog_jobs" in body
    assert body["groups"][0]["endpoint"] == "/ingest/transactions"


async def test_ingestion_stalled_jobs(async_test_client: httpx.AsyncClient):
    response = await async_test_client.get("/ingestion/health/stalled-jobs")
    assert response.status_code == 200
    body = response.json()
    assert "jobs" in body
    assert "threshold_seconds" in body
    assert body["jobs"][0]["status"] == "accepted"


async def test_ingestion_ops_control_mode_blocks_writes(
    async_test_client: httpx.AsyncClient,
):
    update_response = await async_test_client.put(
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

    restore_response = await async_test_client.put(
        "/ingestion/ops/control",
        json={"mode": "normal", "updated_by": "test"},
    )
    assert restore_response.status_code == 200


async def test_ingestion_consumer_dlq_events_endpoint(async_test_client: httpx.AsyncClient):
    response = await async_test_client.get("/ingestion/dlq/consumer-events")
    assert response.status_code == 200
    body = response.json()
    assert "events" in body
    assert "total" in body


async def test_ingestion_consumer_lag_endpoint(async_test_client: httpx.AsyncClient):
    response = await async_test_client.get("/ingestion/health/consumer-lag")
    assert response.status_code == 200
    body = response.json()
    assert "groups" in body
    assert "backlog_jobs" in body


async def test_ingestion_error_budget_endpoint(async_test_client: httpx.AsyncClient):
    response = await async_test_client.get("/ingestion/health/error-budget")
    assert response.status_code == 200
    body = response.json()
    assert "failure_rate" in body
    assert "remaining_error_budget" in body
    assert "replay_backlog_pressure_ratio" in body
    assert "dlq_events_in_window" in body
    assert "dlq_budget_events_per_window" in body
    assert "dlq_pressure_ratio" in body


async def test_ingestion_operating_band_endpoint(async_test_client: httpx.AsyncClient):
    response = await async_test_client.get("/ingestion/health/operating-band")
    assert response.status_code == 200
    body = response.json()
    assert body["operating_band"] in {"green", "yellow", "orange", "red"}
    assert "recommended_action" in body
    assert "triggered_signals" in body


async def test_ingestion_idempotency_diagnostics_endpoint(async_test_client: httpx.AsyncClient):
    response = await async_test_client.get("/ingestion/idempotency/diagnostics")
    assert response.status_code == 200
    body = response.json()
    assert "keys" in body
    assert "collisions" in body


async def test_ingestion_job_records_endpoint(async_test_client: httpx.AsyncClient):
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
    response = await async_test_client.get(f"/ingestion/jobs/{job_id}/records")
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == job_id
    assert "replayable_record_keys" in body


async def test_replay_consumer_dlq_event_endpoint(async_test_client: httpx.AsyncClient):
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
    response = await async_test_client.post(
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
    first = await async_test_client.post(
        "/ingestion/dlq/consumer-events/cdlq_test_001/replay",
        json={"dry_run": False},
    )
    assert first.status_code == 200
    second = await async_test_client.post(
        "/ingestion/dlq/consumer-events/cdlq_test_001/replay",
        json={"dry_run": False},
    )
    assert second.status_code == 200
    body = second.json()
    assert body["replay_status"] == "duplicate_blocked"


async def test_ingestion_replay_audit_list_and_get(async_test_client: httpx.AsyncClient):
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
    replay_response = await async_test_client.post(
        "/ingestion/dlq/consumer-events/cdlq_test_001/replay",
        json={"dry_run": True},
    )
    assert replay_response.status_code == 200
    replay_id = replay_response.json()["replay_audit_id"]

    list_response = await async_test_client.get(
        "/ingestion/audit/replays",
        params={"recovery_path": "consumer_dlq_replay"},
    )
    assert list_response.status_code == 200
    audits = list_response.json()["audits"]
    assert any(item["replay_id"] == replay_id for item in audits)

    get_response = await async_test_client.get(f"/ingestion/audit/replays/{replay_id}")
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


async def test_ingestion_ops_supports_bearer_jwt(async_test_client: httpx.AsyncClient, monkeypatch):
    now_epoch = int(datetime.now(UTC).timestamp())
    secret = "test-hs256-secret"
    for module in {ops_controls, app_ops_controls}:
        monkeypatch.setattr(module, "OPS_AUTH_MODE", "token_or_jwt")
        monkeypatch.setattr(module, "OPS_JWT_HS256_SECRET", secret)
        monkeypatch.setattr(module, "OPS_JWT_ISSUER", "")
        monkeypatch.setattr(module, "OPS_JWT_AUDIENCE", "")
    payload = {"sub": "ops-jwt-user", "exp": now_epoch + 600}
    token = _build_hs256_jwt(secret, payload)

    response = await async_test_client.get(
        "/ingestion/health/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


async def test_ingest_instruments_endpoint(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    """Tests the POST /ingest/instruments endpoint."""
    mock_kafka_producer.publish_message.reset_mock()
    payload = {
        "instruments": [
            {
                "security_id": "S1",
                "name": "N1",
                "isin": "I1",
                "currency": "USD",
                "product_type": "E",
            }
        ]
    }

    response = await async_test_client.post("/ingest/instruments", json=payload)

    assert response.status_code == 202
    mock_kafka_producer.publish_message.assert_called_once()


async def test_ingest_market_prices_endpoint(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    """Tests the POST /ingest/market-prices endpoint."""
    mock_kafka_producer.publish_message.reset_mock()
    payload = {
        "market_prices": [
            {"security_id": "S1", "price_date": "2025-01-01", "price": 100, "currency": "USD"}
        ]
    }

    response = await async_test_client.post("/ingest/market-prices", json=payload)

    assert response.status_code == 202
    mock_kafka_producer.publish_message.assert_called_once()


async def test_ingest_fx_rates_endpoint(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    """Tests the POST /ingest/fx-rates endpoint."""
    mock_kafka_producer.publish_message.reset_mock()
    payload = {
        "fx_rates": [
            {"from_currency": "USD", "to_currency": "EUR", "rate_date": "2025-01-01", "rate": 0.9}
        ]
    }

    response = await async_test_client.post("/ingest/fx-rates", json=payload)

    assert response.status_code == 202
    mock_kafka_producer.publish_message.assert_called_once()


async def test_ingest_portfolio_bundle_endpoint(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    """Tests the POST /ingest/portfolio-bundle endpoint."""
    mock_kafka_producer.publish_message.reset_mock()
    payload = {
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

    response = await async_test_client.post("/ingest/portfolio-bundle", json=payload)

    assert response.status_code == 202
    body = response.json()
    assert body["entity_type"] == "portfolio_bundle"
    assert body["accepted_count"] == 6
    assert "job_id" in body
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
