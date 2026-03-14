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
