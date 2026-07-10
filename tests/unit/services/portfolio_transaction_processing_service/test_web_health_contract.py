from __future__ import annotations

import importlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from portfolio_common import health

from src.services.portfolio_transaction_processing_service.app import web

SECURITY_COVERAGE_CONTRACT = Path("contracts/security/security-control-coverage.v1.json")


def test_combined_health_app_has_explicit_health_only_security_coverage() -> None:
    contract = json.loads(SECURITY_COVERAGE_CONTRACT.read_text(encoding="utf-8"))
    entry = next(
        item
        for item in contract["apps"]
        if item["service_name"] == "portfolio_transaction_processing_service_web"
    )

    assert entry == {
        "service_name": "portfolio_transaction_processing_service_web",
        "app_path": "src/services/portfolio_transaction_processing_service/app/web.py",
        "app_kind": "health_only_worker_api",
        "auth_audit_control": "health_only_no_business_routes",
        "payload_limit_control": "not_applicable_health_only",
        "upload_limit_control": "not_applicable",
        "unauthenticated_allowlist": [
            "/docs",
            "/health/live",
            "/health/ready",
            "/metrics",
            "/openapi.json",
            "/redoc",
            "/version",
        ],
    }


def _build_metadata_environment(monkeypatch) -> dict[str, str]:
    values = {
        "LOTUS_GIT_COMMIT_SHA": "0123456789abcdef0123456789abcdef01234567",
        "LOTUS_GIT_BRANCH": "refactor/issue-468-calculator-stage-boundaries",
        "LOTUS_BUILD_TIMESTAMP": "2026-07-10T06:00:00Z",
        "LOTUS_REPO_URL": "https://github.com/sgajbi/lotus-core",
        "LOTUS_IMAGE_VERSION": "0123456789abcdef0123456789abcdef01234567",
        "LOTUS_IMAGE_DIGEST": "sha256:abcdef1234567890",
        "LOTUS_CI_RUN_ID": "4681457",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return values


def test_combined_health_app_exposes_ready_dependencies_and_version_metadata(
    monkeypatch,
) -> None:
    metadata = _build_metadata_environment(monkeypatch)
    with (
        patch.object(health, "check_db_health", AsyncMock(return_value=True)),
        patch.object(health, "check_kafka_health", AsyncMock(return_value=True)),
        patch.object(health, "_database_dependency_configured", return_value=True),
        patch.object(health, "_kafka_dependency_configured", return_value=True),
        patch.object(health, "worker_runtime_configured", return_value=True),
        patch.object(
            health,
            "check_worker_runtime_health_status",
            AsyncMock(return_value="ok"),
        ),
    ):
        target_web = importlib.reload(web)
        client = TestClient(target_web.app)

        ready_response = client.get("/health/ready")
        version_response = client.get("/version")
        openapi = client.get("/openapi.json").json()

    importlib.reload(web)

    assert ready_response.status_code == 200
    assert ready_response.json()["dependencies"] == {
        "database": "ok",
        "kafka": "ok",
        "worker_runtime": "ok",
    }
    assert ready_response.json()["runtime"]["service_name"] == (
        "portfolio_transaction_processing_service_web"
    )
    assert version_response.status_code == 200
    version = version_response.json()
    assert version == ready_response.json()["runtime"]["build"]
    assert version["service_name"] == "portfolio_transaction_processing_service_web"
    assert version["git_commit_sha"] == metadata["LOTUS_GIT_COMMIT_SHA"]
    assert version["git_branch"] == metadata["LOTUS_GIT_BRANCH"]
    assert version["build_timestamp"] == metadata["LOTUS_BUILD_TIMESTAMP"]
    assert version["repo_url"] == metadata["LOTUS_REPO_URL"]
    assert version["image_version"] == metadata["LOTUS_IMAGE_VERSION"]
    assert version["image_digest"] == metadata["LOTUS_IMAGE_DIGEST"]
    assert version["ci_pipeline_run_id"] == metadata["LOTUS_CI_RUN_ID"]
    assert set(openapi["paths"]) >= {
        "/health/live",
        "/health/ready",
        "/metrics",
        "/version",
    }


def test_combined_health_app_fails_readiness_when_runtime_task_failed() -> None:
    with (
        patch.object(health, "check_db_health", AsyncMock(return_value=True)),
        patch.object(health, "check_kafka_health", AsyncMock(return_value=True)),
        patch.object(health, "_database_dependency_configured", return_value=True),
        patch.object(health, "_kafka_dependency_configured", return_value=True),
        patch.object(health, "worker_runtime_configured", return_value=True),
        patch.object(
            health,
            "check_worker_runtime_health_status",
            AsyncMock(return_value="failed"),
        ),
    ):
        target_web = importlib.reload(web)
        response = TestClient(target_web.app).get("/health/ready")

    importlib.reload(web)

    assert response.status_code == 503
    assert response.json()["detail"]["dependencies"] == {
        "database": "ok",
        "kafka": "ok",
        "worker_runtime": "failed",
    }
