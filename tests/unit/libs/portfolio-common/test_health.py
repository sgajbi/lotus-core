import asyncio

import portfolio_common.health as health_module
import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.asyncio


def _readiness_endpoint(router):
    return next(route.endpoint for route in router.routes if route.path == "/health/ready")


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
    assert exc_info.value.detail == {
        "status": "not_ready",
        "dependencies": {"database": "ok", "kafka": "unavailable"},
    }


async def test_readiness_probe_returns_ready_for_known_dependencies_only():
    router = health_module.create_health_router("unknown")
    readiness_probe = _readiness_endpoint(router)

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
    readiness_probe = _readiness_endpoint(router)

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
    readiness_probe = _readiness_endpoint(router)

    await readiness_probe()
    now = 106.0
    await readiness_probe()

    assert calls == 2


async def test_readiness_probe_classifies_db_timeout(monkeypatch):
    async def _db_slow():
        await asyncio.sleep(0.05)
        return True

    monkeypatch.setattr(health_module, "check_db_health", _db_slow)

    router = health_module.create_health_router(
        "db",
        readiness_cache_ttl_seconds=0,
        readiness_dependency_timeout_seconds=0.001,
    )
    readiness_probe = _readiness_endpoint(router)

    with pytest.raises(HTTPException) as exc_info:
        await readiness_probe()

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == {
        "status": "not_ready",
        "dependencies": {"database": "timeout"},
    }


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
    assert exc_info.value.detail == {
        "status": "not_ready",
        "dependencies": {"kafka": "timeout"},
    }


async def test_readiness_probe_classifies_dependency_exception(monkeypatch):
    async def _db_error():
        raise RuntimeError("boom")

    monkeypatch.setattr(health_module, "check_db_health", _db_error)

    router = health_module.create_health_router(
        "db",
        readiness_cache_ttl_seconds=0,
    )
    readiness_probe = _readiness_endpoint(router)

    with pytest.raises(HTTPException) as exc_info:
        await readiness_probe()

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == {
        "status": "not_ready",
        "dependencies": {"database": "error"},
    }


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

    assert (
        first_exc_info.value.detail
        == second_exc_info.value.detail
        == {
            "status": "not_ready",
            "dependencies": {"database": "unavailable"},
        }
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
    assert exc_info.value.detail == {
        "status": "not_ready",
        "dependencies": {"database": "ok", "kafka": "error"},
    }
