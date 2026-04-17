from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio

from src.services.event_replay_service.app.main import app, lifespan

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_middleware_preserves_incoming_correlation_id(async_test_client):
    response = await async_test_client.get(
        "/openapi.json", headers={"X-Correlation-ID": "corr-123"}
    )

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "corr-123"


async def test_middleware_generates_correlation_id_when_missing(async_test_client):
    with patch(
        "src.services.event_replay_service.app.main.generate_correlation_id",
        return_value="ERP-abc",
    ):
        response = await async_test_client.get("/openapi.json")

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "ERP-abc"


async def test_middleware_replaces_unset_lineage_headers(async_test_client):
    with patch(
        "src.services.event_replay_service.app.main.generate_correlation_id",
        side_effect=["ERP-abc", "REQ-abc"],
    ):
        response = await async_test_client.get(
            "/openapi.json",
            headers={
                "X-Correlation-ID": "<not-set>",
                "X-Request-Id": "",
                "X-Trace-Id": "<not-set>",
            },
        )

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "ERP-abc"
    assert response.headers["X-Request-Id"] == "REQ-abc"
    assert response.headers["X-Trace-Id"] not in ("", "<not-set>")


async def test_lifespan_logs_startup_and_shutdown():
    with patch("src.services.event_replay_service.app.main.logger.info") as logger_info:
        async with lifespan(app):
            pass

    logged_messages = [args[0] for args, _ in logger_info.call_args_list]
    assert "Event Replay Service starting up..." in logged_messages
    assert any("shutting down" in message for message in logged_messages)
    assert "Event Replay Service has shut down gracefully." in logged_messages


async def test_openapi_contains_replay_control_plane_endpoints(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/ingestion/jobs" in paths
    assert "/ingestion/jobs/{job_id}/retry" in paths
    assert "/ingestion/dlq/consumer-events/{event_id}/replay" in paths
    assert "/ingestion/health/policy" in paths
    assert "/ingestion/audit/replays" in paths


async def test_openapi_includes_replay_examples(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    retry_operation = schema["paths"]["/ingestion/jobs/{job_id}/retry"]["post"]
    retry_examples = retry_operation["requestBody"]["content"]["application/json"]["examples"]
    retry_response_example = retry_operation["responses"]["200"]["content"]["application/json"][
        "example"
    ]
    assert "partial_dry_run" in retry_examples
    assert retry_examples["partial_dry_run"]["value"]["dry_run"] is True
    assert retry_response_example["job_id"] == "job_01J5S0J6D3BAVMK2E1V0WQ7MCC"

    replay_operation = schema["paths"]["/ingestion/dlq/consumer-events/{event_id}/replay"]["post"]
    replay_examples = replay_operation["requestBody"]["content"]["application/json"]["examples"]
    replay_response_example = replay_operation["responses"]["200"]["content"]["application/json"][
        "example"
    ]
    assert "replay_now" in replay_examples
    assert replay_response_example["replay_status"] == "replayed"

    ops_control_example = schema["paths"]["/ingestion/ops/control"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["example"]
    assert ops_control_example["mode"] == "paused"


async def test_openapi_describes_event_replay_operational_parameters(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    get_job = schema["paths"]["/ingestion/jobs/{job_id}"]["get"]
    list_failures = schema["paths"]["/ingestion/jobs/{job_id}/failures"]["get"]
    get_records = schema["paths"]["/ingestion/jobs/{job_id}/records"]["get"]
    retry_job = schema["paths"]["/ingestion/jobs/{job_id}/retry"]["post"]
    health_summary = schema["paths"]["/ingestion/health/summary"]["get"]
    health_lag = schema["paths"]["/ingestion/health/lag"]["get"]
    consumer_lag = schema["paths"]["/ingestion/health/consumer-lag"]["get"]
    slo_status = schema["paths"]["/ingestion/health/slo"]["get"]
    error_budget = schema["paths"]["/ingestion/health/error-budget"]["get"]
    replay_dlq = schema["paths"]["/ingestion/dlq/consumer-events/{event_id}/replay"]["post"]
    list_jobs = schema["paths"]["/ingestion/jobs"]["get"]

    job_id_parameter = next(param for param in get_job["parameters"] if param["name"] == "job_id")
    assert get_job["summary"] == "Get ingestion job status"
    assert "track asynchronous ingestion completion or failure" in get_job["description"]
    assert job_id_parameter["description"] == "Ingestion job identifier."
    job_not_found = get_job["responses"]["404"]["content"]["application/json"]["example"]
    assert job_not_found["detail"]["code"] == "INGESTION_JOB_NOT_FOUND"

    def _enum_values(parameter_schema: dict) -> list[str]:
        if "enum" in parameter_schema:
            return parameter_schema["enum"]
        for candidate in parameter_schema.get("anyOf", []):
            values = _enum_values(candidate)
            if values:
                return values
        return []

    def _schema_bound(parameter_schema: dict, bound: str):
        if bound in parameter_schema:
            return parameter_schema[bound]
        for candidate in parameter_schema.get("anyOf", []):
            if bound in candidate:
                return candidate[bound]
        raise AssertionError(f"Schema bound {bound} not found in {parameter_schema}")

    status_parameter = next(param for param in list_jobs["parameters"] if param["name"] == "status")
    assert status_parameter["description"] == "Optional job status filter."
    assert _enum_values(status_parameter["schema"]) == ["accepted", "queued", "failed"]

    entity_type_parameter = next(
        param for param in list_jobs["parameters"] if param["name"] == "entity_type"
    )
    assert entity_type_parameter["description"] == "Optional canonical entity type filter."

    submitted_from_parameter = next(
        param for param in list_jobs["parameters"] if param["name"] == "submitted_from"
    )
    assert submitted_from_parameter["description"] == (
        "Optional inclusive lower bound for job submission timestamp."
    )

    submitted_to_parameter = next(
        param for param in list_jobs["parameters"] if param["name"] == "submitted_to"
    )
    assert submitted_to_parameter["description"] == (
        "Optional inclusive upper bound for job submission timestamp."
    )

    cursor_parameter = next(param for param in list_jobs["parameters"] if param["name"] == "cursor")
    assert cursor_parameter["description"] == "Opaque pagination cursor from the previous page."

    limit_parameter = next(param for param in list_jobs["parameters"] if param["name"] == "limit")
    assert limit_parameter["schema"]["minimum"] == 1
    assert limit_parameter["schema"]["maximum"] == 500

    failure_job_id_parameter = next(
        param for param in list_failures["parameters"] if param["name"] == "job_id"
    )
    failure_limit_parameter = next(
        param for param in list_failures["parameters"] if param["name"] == "limit"
    )
    failure_example = list_failures["responses"]["200"]["content"]["application/json"]["example"]
    failure_not_found = list_failures["responses"]["404"]["content"]["application/json"]["example"]
    assert list_failures["summary"] == "List ingestion job failures"
    assert "failure history with most-recent-first ordering" in list_failures["description"]
    assert failure_job_id_parameter["description"] == "Ingestion job identifier."
    assert failure_limit_parameter["schema"]["minimum"] == 1
    assert failure_limit_parameter["schema"]["maximum"] == 500
    assert failure_example["failures"][0]["failure_phase"] == "publish"
    assert failure_example["failures"][0]["failed_record_keys"] == [
        "TXN-2026-000145",
        "TXN-2026-000146",
    ]
    assert failure_not_found["detail"]["code"] == "INGESTION_JOB_NOT_FOUND"

    record_job_id_parameter = next(
        param for param in get_records["parameters"] if param["name"] == "job_id"
    )
    record_example = get_records["responses"]["200"]["content"]["application/json"]["example"]
    record_not_found = get_records["responses"]["404"]["content"]["application/json"]["example"]
    assert get_records["summary"] == "Get ingestion job record-level status"
    assert "Derive replayable keys from stored payload" in get_records["description"]
    assert record_job_id_parameter["description"] == "Ingestion job identifier."
    assert record_example["accepted_count"] == 3
    assert record_example["failed_record_keys"] == [
        "TXN-2026-000145",
        "TXN-2026-000146",
    ]
    assert record_example["replayable_record_keys"] == [
        "TXN-2026-000145",
        "TXN-2026-000146",
        "TXN-2026-000147",
    ]
    assert record_not_found["detail"]["code"] == "INGESTION_JOB_NOT_FOUND"

    retry_conflict_examples = retry_job["responses"]["409"]["content"]["application/json"][
        "examples"
    ]
    retry_bookkeeping_failed = retry_job["responses"]["500"]["content"]["application/json"][
        "example"
    ]
    retry_body_schema = retry_job["requestBody"]["content"]["application/json"]["schema"]
    assert retry_job["summary"] == "Retry a failed ingestion job"
    assert "full or partial payload replay" in retry_job["description"]
    assert retry_body_schema["$ref"].endswith("/IngestionRetryRequest")
    assert "retry_unsupported" in retry_conflict_examples
    assert "partial_retry_unsupported" in retry_conflict_examples
    assert "retry_blocked" in retry_conflict_examples
    assert "duplicate_blocked" in retry_conflict_examples
    assert (
        retry_conflict_examples["partial_retry_unsupported"]["value"]["detail"]["code"]
        == "INGESTION_PARTIAL_RETRY_UNSUPPORTED"
    )
    assert (
        retry_conflict_examples["retry_blocked"]["value"]["detail"]["code"]
        == "INGESTION_RETRY_BLOCKED"
    )
    assert retry_bookkeeping_failed["detail"]["code"] == "INGESTION_RETRY_BOOKKEEPING_FAILED"

    health_example = health_summary["responses"]["200"]["content"]["application/json"]["example"]
    assert health_summary["summary"] == "Get ingestion operational health summary"
    assert "fast operational health checks and dashboards" in health_summary["description"]
    assert health_example == {
        "total_jobs": 2450,
        "accepted_jobs": 3,
        "queued_jobs": 7,
        "failed_jobs": 2,
        "backlog_jobs": 10,
        "oldest_backlog_job_id": "job_01J5S0J6D3BAVMK2E1V0WQ7MCC",
    }

    health_lag_example = health_lag["responses"]["200"]["content"]["application/json"]["example"]
    assert health_lag["summary"] == "Get ingestion backlog indicators"
    assert "quick backlog signal during ingestion incidents" in health_lag["description"]
    assert health_lag_example == health_example

    consumer_lag_params = {param["name"]: param for param in consumer_lag["parameters"]}
    consumer_lag_example = consumer_lag["responses"]["200"]["content"]["application/json"][
        "example"
    ]
    assert consumer_lag["summary"] == "Get consumer lag diagnostics"
    assert (
        "triage downstream consumer lag before replaying ingestion jobs"
        in consumer_lag["description"]
    )
    assert consumer_lag_params["lookback_minutes"]["description"] == (
        "Lookback window, in minutes, used to aggregate consumer lag diagnostics."
    )
    assert consumer_lag_params["lookback_minutes"]["schema"]["minimum"] == 5
    assert consumer_lag_params["lookback_minutes"]["schema"]["maximum"] == 1440
    assert consumer_lag_params["limit"]["description"] == (
        "Maximum number of consumer-group/topic lag rows to return."
    )
    assert consumer_lag_params["limit"]["schema"]["minimum"] == 1
    assert consumer_lag_params["limit"]["schema"]["maximum"] == 500
    assert consumer_lag_example["groups"][0]["lag_severity"] == "high"
    assert consumer_lag_example["groups"][1]["lag_severity"] == "medium"

    slo_params = {param["name"]: param for param in slo_status["parameters"]}
    slo_example = slo_status["responses"]["200"]["content"]["application/json"]["example"]
    assert slo_status["summary"] == "Evaluate ingestion SLO status"
    assert "alert evaluation, on-call triage" in slo_status["description"]
    assert slo_params["lookback_minutes"]["schema"]["minimum"] == 5
    assert slo_params["lookback_minutes"]["schema"]["maximum"] == 1440
    assert _schema_bound(slo_params["failure_rate_threshold"]["schema"], "minimum") == 0
    assert _schema_bound(slo_params["failure_rate_threshold"]["schema"], "maximum") == 1
    assert slo_params["queue_latency_threshold_seconds"]["schema"]["minimum"] == 0.1
    assert slo_params["queue_latency_threshold_seconds"]["schema"]["maximum"] == 600
    assert slo_params["backlog_age_threshold_seconds"]["schema"]["minimum"] == 1
    assert slo_params["backlog_age_threshold_seconds"]["schema"]["maximum"] == 86400
    assert slo_example["failure_rate"] == "0.0125"
    assert slo_example["breach_failure_rate"] is False

    error_budget_params = {param["name"]: param for param in error_budget["parameters"]}
    error_budget_example = error_budget["responses"]["200"]["content"]["application/json"][
        "example"
    ]
    assert error_budget["summary"] == "Get ingestion error-budget and backlog-growth status"
    assert "burn-rate alerts and release-go/no-go" in error_budget["description"]
    assert error_budget_params["lookback_minutes"]["schema"]["minimum"] == 5
    assert error_budget_params["lookback_minutes"]["schema"]["maximum"] == 1440
    assert _schema_bound(error_budget_params["failure_rate_threshold"]["schema"], "minimum") == 0
    assert _schema_bound(error_budget_params["failure_rate_threshold"]["schema"], "maximum") == 1
    assert error_budget_params["backlog_growth_threshold"]["schema"]["minimum"] == 0
    assert error_budget_params["backlog_growth_threshold"]["schema"]["maximum"] == 10000
    assert error_budget_example["remaining_error_budget"] == "0.008125"
    assert error_budget_example["dlq_pressure_ratio"] == "0.4000"

    replay_not_found = replay_dlq["responses"]["404"]["content"]["application/json"]["example"]
    assert replay_not_found["detail"]["code"] == "INGESTION_CONSUMER_DLQ_EVENT_NOT_FOUND"


async def test_openapi_describes_event_replay_shared_schema_depth(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()["components"]["schemas"]

    ops_mode = schema["IngestionOpsModeResponse"]
    ops_mode_update = schema["IngestionOpsModeUpdateRequest"]
    retry_request = schema["IngestionRetryRequest"]
    replay_request = schema["ConsumerDlqReplayRequest"]
    replay_audit_list = schema["IngestionReplayAuditListResponse"]
    idempotency = schema["IngestionIdempotencyDiagnosticsResponse"]
    consumer_lag = schema["IngestionConsumerLagResponse"]
    consumer_lag_group = schema["IngestionConsumerLagGroupResponse"]
    slo_status = schema["IngestionSloStatusResponse"]
    error_budget = schema["IngestionErrorBudgetStatusResponse"]

    assert ops_mode["properties"]["mode"]["description"] == (
        "Current ingestion operations mode used to control replay and write-ingress behavior."
    )
    assert ops_mode_update["properties"]["mode"]["description"] == (
        "Target ingestion operations mode to apply."
    )
    assert replay_request["properties"]["dry_run"]["description"] == (
        "When true, validate replayability and replay mapping without republishing messages."
    )
    assert retry_request["properties"]["record_keys"]["description"] == (
        "Optional subset of record keys to replay. Empty list replays full stored payload."
    )
    assert retry_request["properties"]["dry_run"]["description"] == (
        "When true, validates retry scope without publishing messages."
    )
    assert replay_audit_list["properties"]["audits"]["description"] == (
        "Replay audit rows matching the requested filters and time window."
    )
    assert idempotency["properties"]["keys"]["description"] == (
        "Key-level idempotency diagnostics sorted by highest usage count."
    )
    assert consumer_lag["properties"]["groups"]["description"] == (
        "Consumer lag group diagnostics sorted by highest pressure first."
    )
    assert consumer_lag_group["properties"]["dlq_events"]["description"] == (
        "Number of DLQ events for this consumer/topic in lookback window."
    )
    assert consumer_lag_group["properties"]["lag_severity"]["enum"] == [
        "low",
        "medium",
        "high",
    ]
    assert slo_status["properties"]["failure_rate"]["description"] == (
        "Failed jobs divided by total jobs in the lookback window."
    )
    assert slo_status["properties"]["p95_queue_latency_seconds"]["description"] == (
        "95th percentile latency from job submission to queue completion."
    )
    assert slo_status["properties"]["breach_backlog_age"]["description"] == (
        "Whether backlog age exceeds configured threshold."
    )
    assert error_budget["properties"]["remaining_error_budget"]["description"] == (
        "Remaining budget to threshold (max(0, threshold - failure_rate))."
    )
    assert error_budget["properties"]["replay_backlog_pressure_ratio"]["description"] == (
        "Backlog saturation ratio against replay guardrail capacity "
        "(backlog_jobs / replay_max_backlog_jobs)."
    )
    assert error_budget["properties"]["dlq_pressure_ratio"]["description"] == (
        "DLQ pressure ratio against budget (dlq_events_in_window / dlq_budget_events_per_window)."
    )


async def test_openapi_describes_ingestion_job_shared_schema_depth(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()["components"]["schemas"]

    job_detail = schema["IngestionJobResponse"]
    job_failure = schema["IngestionJobFailureResponse"]
    job_failure_list = schema["IngestionJobFailureListResponse"]
    job_list = schema["IngestionJobListResponse"]
    job_record_status = schema["IngestionJobRecordStatusResponse"]
    health_summary = schema["IngestionHealthSummaryResponse"]
    ops_policy = schema["IngestionOpsPolicyResponse"]
    queue_health = schema["IngestionReprocessingQueueHealthResponse"]

    assert set(job_detail["required"]) == {
        "job_id",
        "endpoint",
        "entity_type",
        "status",
        "accepted_count",
        "correlation_id",
        "request_id",
        "trace_id",
        "submitted_at",
        "retry_count",
    }
    assert job_detail["properties"]["endpoint"]["description"] == (
        "Ingestion API endpoint that created this job."
    )
    assert job_detail["properties"]["accepted_count"]["minimum"] == 0
    assert job_detail["properties"]["status"]["enum"] == ["accepted", "queued", "failed"]
    assert job_detail["properties"]["failure_reason"]["description"] == (
        "Failure reason when status is failed."
    )
    assert job_detail["properties"]["last_retried_at"]["description"] == (
        "Timestamp of the most recent retry attempt."
    )
    assert job_list["properties"]["jobs"]["description"] == (
        "Ingestion jobs matching the requested filters and pagination window."
    )
    assert job_list["properties"]["total"]["description"] == (
        "Number of jobs returned in this response."
    )
    assert job_list["properties"]["next_cursor"]["description"] == (
        "Opaque cursor to fetch the next page of jobs, based on descending ingestion job order."
    )
    assert job_failure["properties"]["failure_phase"]["description"] == (
        "Pipeline phase where the job failure occurred."
    )
    assert job_failure["properties"]["failed_record_keys"]["description"] == (
        "Record keys that failed during publish/retry processing, including batch records "
        "left unpublished after a mid-batch publish failure."
    )
    assert job_failure_list["properties"]["failures"]["description"] == (
        "Failure events captured for the requested ingestion job."
    )
    assert job_failure_list["properties"]["total"]["description"] == (
        "Number of failure events returned in this response."
    )
    assert job_record_status["properties"]["accepted_count"]["description"] == (
        "Number of records accepted by the original ingestion request."
    )
    assert job_record_status["properties"]["failed_record_keys"]["description"] == (
        "Record keys failed across publish/retry lifecycle."
    )
    assert job_record_status["properties"]["replayable_record_keys"]["description"] == (
        "Record keys available for deterministic partial replay operations."
    )
    assert health_summary["properties"]["total_jobs"]["description"] == (
        "Total ingestion jobs stored in operational state."
    )
    assert health_summary["properties"]["accepted_jobs"]["description"] == (
        "Total jobs currently in accepted state."
    )
    assert health_summary["properties"]["queued_jobs"]["description"] == (
        "Total jobs currently queued for asynchronous processing."
    )
    assert health_summary["properties"]["failed_jobs"]["description"] == (
        "Total jobs currently marked as failed."
    )
    assert health_summary["properties"]["backlog_jobs"]["description"] == (
        "Operational backlog count (accepted + queued)."
    )
    assert health_summary["properties"]["oldest_backlog_job_id"]["description"] == (
        "Identifier of the oldest non-terminal job contributing to the backlog."
    )
    assert ops_policy["properties"]["replay_dry_run_supported"]["description"] == (
        "Whether replay dry-run mode is supported by the active control plane."
    )
    assert queue_health["properties"]["queues"]["description"] == (
        "Per-job-type queue health rows sorted by highest pending pressure."
    )


async def test_openapi_excludes_write_ingress_endpoints(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/ingest/transactions" not in paths
    assert "/ingest/portfolios" not in paths
    assert "/ingest/instruments" not in paths
