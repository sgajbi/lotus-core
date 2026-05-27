import portfolio_common.health as health_module
import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.asyncio


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
        readiness_probe = next(
            route.endpoint for route in router.routes if route.path == "/health/ready"
        )
        with pytest.raises(HTTPException) as exc_info:
            await readiness_probe()
    finally:
        health_module.check_db_health = original_db
        health_module.check_kafka_health = original_kafka

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == {
        "status": "not_ready",
        "dependencies": {"database": "ok", "kafka": "unavailable"},
    }


async def test_readiness_probe_returns_ready_for_known_dependencies_only():
    router = health_module.create_health_router("unknown")
    readiness_probe = next(
        route.endpoint for route in router.routes if route.path == "/health/ready"
    )

    response = await readiness_probe()

    assert response == {"status": "ready", "dependencies": {}}


async def test_readiness_probe_caches_dependency_results_within_ttl(monkeypatch):
    calls = 0
    now = 100.0

    async def _db_ok():
        nonlocal calls
        calls += 1
        return True

    monkeypatch.setattr(health_module, "check_db_health", _db_ok)
    monkeypatch.setattr(health_module.time, "monotonic", lambda: now)

    router = health_module.create_health_router("db", readiness_cache_ttl_seconds=5.0)
    readiness_probe = next(
        route.endpoint for route in router.routes if route.path == "/health/ready"
    )

    assert await readiness_probe() == {"status": "ready", "dependencies": {"database": "ok"}}
    assert await readiness_probe() == {"status": "ready", "dependencies": {"database": "ok"}}

    assert calls == 1


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
    readiness_probe = next(
        route.endpoint for route in router.routes if route.path == "/health/ready"
    )

    await readiness_probe()
    now = 106.0
    await readiness_probe()

    assert calls == 2
