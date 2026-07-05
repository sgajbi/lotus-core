import asyncio
from unittest.mock import MagicMock

import portfolio_common.health as health_module
import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _stable_health_metadata_env(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.delenv("LOTUS_RUNTIME_PROFILE", raising=False)
    for env_name in (
        "LOTUS_GIT_COMMIT_SHA",
        "LOTUS_GIT_BRANCH",
        "LOTUS_BUILD_TIMESTAMP",
        "LOTUS_REPO_URL",
        "LOTUS_IMAGE_VERSION",
        "LOTUS_IMAGE_DIGEST",
        "LOTUS_CI_RUN_ID",
    ):
        monkeypatch.delenv(env_name, raising=False)


def _readiness_endpoint(router):
    return next(route.endpoint for route in router.routes if route.path == "/health/ready")


def _liveness_endpoint(router):
    return next(route.endpoint for route in router.routes if route.path == "/health/live")


def _assert_runtime_metadata(
    payload: dict,
    *,
    service_name: str = "lotus-core-service",
    app_version: str = "unknown",
) -> None:
    runtime = payload["runtime"]
    assert runtime["service_name"] == service_name
    assert runtime["app_version"] == app_version
    assert runtime["environment"] == "local"
    assert runtime["runtime_profile"] == "local"
    assert runtime["started_at_utc"].endswith("Z")
    assert runtime["uptime_seconds"] >= 0
    build = runtime["build"]
    assert build["service_name"] == service_name
    assert build["git_commit_sha"] == "unknown"
    assert build["git_branch"] == "unknown"
    assert build["build_timestamp"] == "unknown"
    assert build["repo_url"] == "unknown"
    assert build["image_version"] == "unknown"
    assert build["image_digest"] == "unknown"
    assert build["ci_pipeline_run_id"] == "unknown"
    assert build["oci_labels"]["org.opencontainers.image.revision"] == "unknown"


def _assert_ready_payload(
    payload: dict,
    *,
    dependencies: dict[str, str],
    service_name: str = "lotus-core-service",
    app_version: str = "unknown",
) -> None:
    assert payload["status"] == "ready"
    assert payload["dependencies"] == dependencies
    _assert_runtime_metadata(payload, service_name=service_name, app_version=app_version)


def _assert_not_ready_payload(
    payload: dict,
    *,
    dependencies: dict[str, str],
    service_name: str = "lotus-core-service",
    app_version: str = "unknown",
) -> None:
    assert payload["status"] == "not_ready"
    assert payload["dependencies"] == dependencies
    _assert_runtime_metadata(payload, service_name=service_name, app_version=app_version)


async def test_liveness_probe_includes_safe_runtime_metadata(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.delenv("LOTUS_RUNTIME_PROFILE", raising=False)
    router = health_module.create_health_router(
        service_name="query_service",
        app_version="0.2.0",
    )
    liveness_probe = _liveness_endpoint(router)

    response = await liveness_probe()

    assert response["status"] == "alive"
    _assert_runtime_metadata(response, service_name="query_service", app_version="0.2.0")


async def test_readiness_probe_ignores_unknown_dependencies_between_valid_checks():
    async def _db_ok():
        return True

    async def _kafka_down():
        return False

    original_db = health_module.check_db_health
    original_kafka = health_module.check_kafka_health
    health_module.check_db_health = _db_ok
    health_module.check_kafka_health = _kafka_down
    try:
        router = health_module.create_health_router("db", "unknown", "kafka")
        readiness_probe = _readiness_endpoint(router)
        with pytest.raises(HTTPException) as exc_info:
            await readiness_probe()
    finally:
        health_module.check_db_health = original_db
        health_module.check_kafka_health = original_kafka

    assert exc_info.value.status_code == 503
    _assert_not_ready_payload(
        exc_info.value.detail,
        dependencies={"database": "ok", "kafka": "unavailable"},
    )


async def test_readiness_probe_returns_ready_for_known_dependencies_only():
    router = health_module.create_health_router("unknown")
    readiness_probe = _readiness_endpoint(router)

    response = await readiness_probe()

    _assert_ready_payload(response, dependencies={})


async def test_readiness_probe_caches_dependency_results_within_ttl(monkeypatch):
    calls = 0
    now = 100.0
    observe_health_dependency_check = MagicMock()
    set_health_readiness_state = MagicMock()

    async def _db_ok():
        nonlocal calls
        calls += 1
        return True

    monkeypatch.setattr(health_module, "check_db_health", _db_ok)
    monkeypatch.setattr(health_module.time, "monotonic", lambda: now)
    monkeypatch.setattr(
        health_module,
        "observe_health_dependency_check",
        observe_health_dependency_check,
    )
    monkeypatch.setattr(health_module, "set_health_readiness_state", set_health_readiness_state)

    router = health_module.create_health_router(
        "db",
        service_name="query_service",
        readiness_cache_ttl_seconds=5.0,
    )
    readiness_probe = _readiness_endpoint(router)

    _assert_ready_payload(
        await readiness_probe(),
        dependencies={"database": "ok"},
        service_name="query_service",
    )
    _assert_ready_payload(
        await readiness_probe(),
        dependencies={"database": "ok"},
        service_name="query_service",
    )

    assert calls == 1
    observe_health_dependency_check.assert_called_once()
    assert observe_health_dependency_check.call_args.kwargs["service"] == "query_service"
    assert observe_health_dependency_check.call_args.kwargs["dependency"] == "database"
    assert observe_health_dependency_check.call_args.kwargs["status"] == "ok"
    assert observe_health_dependency_check.call_args.kwargs["duration_seconds"] >= 0
    assert set_health_readiness_state.call_count == 2
    assert [call.kwargs for call in set_health_readiness_state.call_args_list] == [
        {"service": "query_service", "state": "ready"},
        {"service": "query_service", "state": "ready"},
    ]


async def test_readiness_probe_rechecks_dependencies_after_ttl(monkeypatch):
    calls = 0
    now = 100.0

    async def _db_ok():
        nonlocal calls
        calls += 1
        return True

    def _monotonic():
        return now

    monkeypatch.setattr(health_module, "check_db_health", _db_ok)
    monkeypatch.setattr(health_module.time, "monotonic", _monotonic)

    router = health_module.create_health_router("db", readiness_cache_ttl_seconds=5.0)
    readiness_probe = _readiness_endpoint(router)

    await readiness_probe()
    now = 106.0
    await readiness_probe()

    assert calls == 2


async def test_readiness_probe_classifies_db_timeout(monkeypatch):
    observe_health_dependency_check = MagicMock()

    async def _db_slow():
        await asyncio.sleep(0.05)
        return True

    monkeypatch.setattr(health_module, "check_db_health", _db_slow)
    monkeypatch.setattr(
        health_module,
        "observe_health_dependency_check",
        observe_health_dependency_check,
    )

    router = health_module.create_health_router(
        "db",
        service_name="query_service",
        readiness_cache_ttl_seconds=0,
        readiness_dependency_timeout_seconds=0.001,
    )
    readiness_probe = _readiness_endpoint(router)

    with pytest.raises(HTTPException) as exc_info:
        await readiness_probe()

    assert exc_info.value.status_code == 503
    _assert_not_ready_payload(
        exc_info.value.detail,
        dependencies={"database": "timeout"},
        service_name="query_service",
    )
    observe_health_dependency_check.assert_called_once()
    assert observe_health_dependency_check.call_args.kwargs["service"] == "query_service"
    assert observe_health_dependency_check.call_args.kwargs["dependency"] == "database"
    assert observe_health_dependency_check.call_args.kwargs["status"] == "timeout"
    assert observe_health_dependency_check.call_args.kwargs["duration_seconds"] >= 0


async def test_readiness_probe_classifies_kafka_timeout(monkeypatch):
    async def _kafka_slow():
        await asyncio.sleep(0.05)
        return True

    monkeypatch.setattr(health_module, "check_kafka_health", _kafka_slow)

    router = health_module.create_health_router(
        "kafka",
        readiness_cache_ttl_seconds=0,
        readiness_dependency_timeout_seconds=0.001,
    )
    readiness_probe = _readiness_endpoint(router)

    with pytest.raises(HTTPException) as exc_info:
        await readiness_probe()

    assert exc_info.value.status_code == 503
    _assert_not_ready_payload(exc_info.value.detail, dependencies={"kafka": "timeout"})


async def test_kafka_health_uses_downstream_request_timeout(monkeypatch):
    monkeypatch.setenv("LOTUS_CORE_DOWNSTREAM_REQUEST_TIMEOUT_MS", "1234")
    admin_client = MagicMock()
    admin_client_cls = MagicMock(return_value=admin_client)
    monkeypatch.setattr(health_module, "AdminClient", admin_client_cls)

    assert await health_module.check_kafka_health() is True

    admin_client.list_topics.assert_called_once_with(timeout=1.234)


async def test_readiness_probe_classifies_kafka_misconfiguration(monkeypatch):
    observe_health_dependency_check = MagicMock()

    async def _kafka_should_not_run():
        raise AssertionError("Kafka readiness probe should not run when config is empty.")

    monkeypatch.setattr(health_module, "KAFKA_BOOTSTRAP_SERVERS", "")
    monkeypatch.setattr(health_module, "check_kafka_health", _kafka_should_not_run)
    monkeypatch.setattr(
        health_module,
        "observe_health_dependency_check",
        observe_health_dependency_check,
    )

    router = health_module.create_health_router(
        "kafka",
        service_name="event_replay_service",
        readiness_cache_ttl_seconds=0,
    )
    readiness_probe = _readiness_endpoint(router)

    with pytest.raises(HTTPException) as exc_info:
        await readiness_probe()

    assert exc_info.value.status_code == 503
    _assert_not_ready_payload(
        exc_info.value.detail,
        dependencies={"kafka": "misconfigured"},
        service_name="event_replay_service",
    )
    observe_health_dependency_check.assert_called_once()
    assert observe_health_dependency_check.call_args.kwargs["service"] == "event_replay_service"
    assert observe_health_dependency_check.call_args.kwargs["dependency"] == "kafka"
    assert observe_health_dependency_check.call_args.kwargs["status"] == "misconfigured"


async def test_readiness_probe_classifies_dependency_exception(monkeypatch):
    observe_health_dependency_check = MagicMock()
    set_health_readiness_state = MagicMock()

    async def _db_error():
        raise RuntimeError("boom")

    monkeypatch.setattr(health_module, "check_db_health", _db_error)
    monkeypatch.setattr(
        health_module,
        "observe_health_dependency_check",
        observe_health_dependency_check,
    )
    monkeypatch.setattr(health_module, "set_health_readiness_state", set_health_readiness_state)

    router = health_module.create_health_router(
        "db",
        service_name="query_service",
        readiness_cache_ttl_seconds=0,
    )
    readiness_probe = _readiness_endpoint(router)

    with pytest.raises(HTTPException) as exc_info:
        await readiness_probe()

    assert exc_info.value.status_code == 503
    _assert_not_ready_payload(
        exc_info.value.detail,
        dependencies={"database": "error"},
        service_name="query_service",
    )
    observe_health_dependency_check.assert_called_once()
    assert observe_health_dependency_check.call_args.kwargs["service"] == "query_service"
    assert observe_health_dependency_check.call_args.kwargs["dependency"] == "database"
    assert observe_health_dependency_check.call_args.kwargs["status"] == "error"
    set_health_readiness_state.assert_called_once_with(
        service="query_service",
        state="not_ready",
    )


async def test_readiness_probe_caches_not_ready_dependency_results(monkeypatch):
    calls = 0
    now = 100.0

    async def _db_down():
        nonlocal calls
        calls += 1
        return False

    monkeypatch.setattr(health_module, "check_db_health", _db_down)
    monkeypatch.setattr(health_module.time, "monotonic", lambda: now)

    router = health_module.create_health_router("db", readiness_cache_ttl_seconds=5.0)
    readiness_probe = _readiness_endpoint(router)

    with pytest.raises(HTTPException) as first_exc_info:
        await readiness_probe()
    with pytest.raises(HTTPException) as second_exc_info:
        await readiness_probe()

    _assert_not_ready_payload(
        first_exc_info.value.detail,
        dependencies={"database": "unavailable"},
    )
    _assert_not_ready_payload(
        second_exc_info.value.detail,
        dependencies={"database": "unavailable"},
    )
    assert calls == 1


async def test_readiness_probe_reports_mixed_dependency_states(monkeypatch):
    async def _db_ok():
        return True

    async def _kafka_error():
        raise RuntimeError("broker failure")

    monkeypatch.setattr(health_module, "check_db_health", _db_ok)
    monkeypatch.setattr(health_module, "check_kafka_health", _kafka_error)

    router = health_module.create_health_router(
        "db",
        "kafka",
        readiness_cache_ttl_seconds=0,
    )
    readiness_probe = _readiness_endpoint(router)

    with pytest.raises(HTTPException) as exc_info:
        await readiness_probe()

    assert exc_info.value.status_code == 503
    _assert_not_ready_payload(
        exc_info.value.detail,
        dependencies={"database": "ok", "kafka": "error"},
    )


async def test_readiness_probe_reports_worker_runtime_failed_state(monkeypatch):
    service_name = "worker_service_web"

    monkeypatch.setattr(
        health_module,
        "worker_runtime_configured",
        lambda service_name: True,
    )

    async def _worker_runtime_failed(*, service_name: str) -> str:
        return "failed"

    monkeypatch.setattr(
        health_module,
        "check_worker_runtime_health_status",
        _worker_runtime_failed,
    )

    router = health_module.create_health_router(
        "worker_runtime",
        service_name=service_name,
        readiness_cache_ttl_seconds=0,
    )
    readiness_probe = _readiness_endpoint(router)

    with pytest.raises(HTTPException) as exc_info:
        await readiness_probe()

    assert exc_info.value.status_code == 503
    _assert_not_ready_payload(
        exc_info.value.detail,
        dependencies={"worker_runtime": "failed"},
        service_name=service_name,
    )


async def test_readiness_probe_reports_unregistered_worker_runtime_misconfigured(monkeypatch):
    monkeypatch.setattr(
        health_module,
        "worker_runtime_configured",
        lambda service_name: False,
    )

    async def _worker_runtime_should_not_run(*, service_name: str) -> str:
        raise AssertionError("worker runtime check should not run without registered tasks")

    monkeypatch.setattr(
        health_module,
        "check_worker_runtime_health_status",
        _worker_runtime_should_not_run,
    )

    router = health_module.create_health_router(
        "worker_runtime",
        service_name="worker_service_web",
        readiness_cache_ttl_seconds=0,
    )
    readiness_probe = _readiness_endpoint(router)

    with pytest.raises(HTTPException) as exc_info:
        await readiness_probe()

    assert exc_info.value.status_code == 503
    _assert_not_ready_payload(
        exc_info.value.detail,
        dependencies={"worker_runtime": "misconfigured"},
        service_name="worker_service_web",
    )
