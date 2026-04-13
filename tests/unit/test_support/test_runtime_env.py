from __future__ import annotations

from tests.test_support.runtime_env import build_test_runtime_env, infer_test_profile


def test_build_test_runtime_env_assigns_dynamic_ports_and_endpoints() -> None:
    runtime_env, endpoints = build_test_runtime_env(
        profile="integration",
        scope="tx-fx",
        env={"LOTUS_TEST_DYNAMIC_PORTS": "true"},
        preserve_existing=False,
    )

    assert runtime_env["LOTUS_TEST_ENV_PROFILE"] == "integration"
    assert runtime_env["COMPOSE_PROJECT_NAME"].startswith("lotus-integration-tx-fx-")
    assert runtime_env["HOST_DATABASE_URL"].startswith("postgresql://user:password@localhost:")
    assert runtime_env["E2E_INGESTION_URL"].startswith("http://localhost:")
    assert runtime_env["KAFKA_BOOTSTRAP_SERVERS"].startswith("localhost:")
    assert runtime_env["LOTUS_PROMETHEUS_HOST_PORT"].isdigit()
    assert runtime_env["LOTUS_GRAFANA_HOST_PORT"].isdigit()
    assert endpoints.compose_project_name == runtime_env["COMPOSE_PROJECT_NAME"]
    assert endpoints.e2e_query_control_plane_url == runtime_env["E2E_QUERY_CONTROL_PLANE_URL"]


def test_build_test_runtime_env_preserves_explicit_overrides() -> None:
    runtime_env, endpoints = build_test_runtime_env(
        profile="e2e",
        scope="rapid",
        env={
            "LOTUS_TEST_DYNAMIC_PORTS": "true",
            "COMPOSE_PROJECT_NAME": "lotus-manual-project",
            "LOTUS_QUERY_HOST_PORT": "18401",
        },
        preserve_existing=True,
    )

    assert runtime_env["COMPOSE_PROJECT_NAME"] == "lotus-manual-project"
    assert runtime_env["LOTUS_QUERY_HOST_PORT"] == "18401"
    assert runtime_env["E2E_QUERY_URL"] == "http://localhost:18401"
    assert endpoints.compose_project_name == "lotus-manual-project"


def test_infer_test_profile_from_args() -> None:
    assert infer_test_profile(["tests/e2e/test_fx_lifecycle.py"]) == "e2e"
    assert infer_test_profile(["tests/integration/tools/test_kafka_setup.py"]) == "integration"
    assert infer_test_profile(["tests/unit/test_support/test_runtime_env.py"]) == "unit"
