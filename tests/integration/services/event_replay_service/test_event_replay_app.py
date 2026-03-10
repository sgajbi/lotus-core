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
    replay_response_example = replay_operation["responses"]["200"]["content"][
        "application/json"
    ]["example"]
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
    retry_job = schema["paths"]["/ingestion/jobs/{job_id}/retry"]["post"]
    replay_dlq = schema["paths"]["/ingestion/dlq/consumer-events/{event_id}/replay"]["post"]
    list_jobs = schema["paths"]["/ingestion/jobs"]["get"]

    job_id_parameter = next(param for param in get_job["parameters"] if param["name"] == "job_id")
    assert job_id_parameter["description"] == "Ingestion job identifier."

    status_parameter = next(param for param in list_jobs["parameters"] if param["name"] == "status")
    assert status_parameter["description"] == "Optional job status filter."

    retry_conflict_examples = retry_job["responses"]["409"]["content"]["application/json"][
        "examples"
    ]
    assert "retry_unsupported" in retry_conflict_examples
    assert "duplicate_blocked" in retry_conflict_examples

    replay_not_found = replay_dlq["responses"]["404"]["content"]["application/json"]["example"]
    assert replay_not_found["detail"]["code"] == "INGESTION_CONSUMER_DLQ_EVENT_NOT_FOUND"


async def test_openapi_describes_event_replay_shared_schema_depth(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()["components"]["schemas"]

    ops_mode = schema["IngestionOpsModeResponse"]
    ops_mode_update = schema["IngestionOpsModeUpdateRequest"]
    replay_request = schema["ConsumerDlqReplayRequest"]
    replay_audit_list = schema["IngestionReplayAuditListResponse"]
    idempotency = schema["IngestionIdempotencyDiagnosticsResponse"]

    assert ops_mode["properties"]["mode"]["description"] == (
        "Current ingestion operations mode used to control replay and write-ingress behavior."
    )
    assert ops_mode_update["properties"]["mode"]["description"] == (
        "Target ingestion operations mode to apply."
    )
    assert replay_request["properties"]["dry_run"]["description"] == (
        "When true, validate replayability and replay mapping without republishing messages."
    )
    assert replay_audit_list["properties"]["audits"]["description"] == (
        "Replay audit rows matching the requested filters and time window."
    )
    assert idempotency["properties"]["keys"]["description"] == (
        "Key-level idempotency diagnostics sorted by highest usage count."
    )


async def test_openapi_excludes_write_ingress_endpoints(async_test_client):
    response = await async_test_client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/ingest/transactions" not in paths
    assert "/ingest/portfolios" not in paths
    assert "/ingest/instruments" not in paths
