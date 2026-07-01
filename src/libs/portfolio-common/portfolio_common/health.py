# src/libs/portfolio-common/portfolio_common/health.py
import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

from confluent_kafka.admin import AdminClient
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from .config import KAFKA_BOOTSTRAP_SERVERS
from .db import AsyncSessionLocal
from .logging_utils import log_operation_event
from .monitoring import observe_health_dependency_check, set_health_readiness_state

logger = logging.getLogger(__name__)

DependencyCheck = Callable[[], Awaitable[bool]]
DependencyConfigurationCheck = Callable[[], bool]

READINESS_OK = "ok"
READINESS_UNAVAILABLE = "unavailable"
READINESS_TIMEOUT = "timeout"
READINESS_ERROR = "error"
READINESS_MISCONFIGURED = "misconfigured"


@dataclass(frozen=True)
class DependencyReadinessResult:
    dependency_name: str
    status: str

    @property
    def is_ready(self) -> bool:
        return self.status == READINESS_OK


class LiveHealthResponse(BaseModel):
    status: str = Field(description="Liveness state for the service process.", examples=["alive"])


class ReadyHealthResponse(BaseModel):
    status: str = Field(
        description="Readiness state for the service and its critical dependencies.",
        examples=["ready"],
    )
    dependencies: dict[str, str] = Field(
        description="Dependency-level readiness results keyed by dependency name.",
        examples=[{"database": "ok", "kafka": "ok"}],
    )


class NotReadyHealthDetail(BaseModel):
    status: str = Field(
        description="Readiness state when at least one dependency is unavailable.",
        examples=["not_ready"],
    )
    dependencies: dict[str, str] = Field(
        description="Dependency-level readiness results keyed by dependency name.",
        examples=[{"database": "ok", "kafka": "timeout"}],
    )


async def check_db_health() -> bool:
    """Checks if a valid async connection can be established with the database."""
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(text("SELECT 1"))
        return True
    except Exception:
        log_operation_event(
            logger,
            logging.ERROR,
            "Health dependency check failed.",
            event_name="health.dependency_check.failed",
            operation="health.readiness",
            status="failed",
            reason_code="database_unavailable",
            dependency="database",
        )
        return False


async def check_kafka_health() -> bool:
    """Checks if a connection can be established with Kafka."""
    try:
        admin_client = AdminClient({"bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS})
        await asyncio.to_thread(admin_client.list_topics, timeout=5)
        return True
    except Exception:
        log_operation_event(
            logger,
            logging.ERROR,
            "Health dependency check failed.",
            event_name="health.dependency_check.failed",
            operation="health.readiness",
            status="failed",
            reason_code="kafka_unavailable",
            dependency="kafka",
        )
        return False


def _database_dependency_configured() -> bool:
    try:
        from .db import get_async_database_url

        return bool(get_async_database_url().strip())
    except Exception:
        return False


def _kafka_dependency_configured() -> bool:
    return bool(KAFKA_BOOTSTRAP_SERVERS.strip())


def _dependency_readiness_result(
    *,
    service_name: str,
    dependency_name: str,
    status_value: str,
    started_at: float,
) -> DependencyReadinessResult:
    observe_health_dependency_check(
        service=service_name,
        dependency=dependency_name,
        status=status_value,
        duration_seconds=time.perf_counter() - started_at,
    )
    return DependencyReadinessResult(dependency_name, status_value)


async def _run_dependency_check(
    dependency_name: str,
    check: DependencyCheck,
    *,
    configuration_check: DependencyConfigurationCheck,
    service_name: str,
    timeout_seconds: float,
) -> DependencyReadinessResult:
    started_at = time.perf_counter()
    if not configuration_check():
        log_operation_event(
            logger,
            logging.ERROR,
            "Health dependency check is misconfigured.",
            event_name="health.dependency_check.misconfigured",
            operation="health.readiness",
            status="misconfigured",
            reason_code="dependency_misconfigured",
            dependency=dependency_name,
        )
        return _dependency_readiness_result(
            service_name=service_name,
            dependency_name=dependency_name,
            status_value=READINESS_MISCONFIGURED,
            started_at=started_at,
        )

    try:
        is_ready = await asyncio.wait_for(check(), timeout=timeout_seconds)
    except TimeoutError:
        log_operation_event(
            logger,
            logging.WARNING,
            "Health dependency check timed out.",
            event_name="health.dependency_check.timeout",
            operation="health.readiness",
            status="timeout",
            reason_code="dependency_timeout",
            dependency=dependency_name,
            timeout_seconds=timeout_seconds,
        )
        return _dependency_readiness_result(
            service_name=service_name,
            dependency_name=dependency_name,
            status_value=READINESS_TIMEOUT,
            started_at=started_at,
        )
    except Exception:
        log_operation_event(
            logger,
            logging.ERROR,
            "Health dependency check failed.",
            event_name="health.dependency_check.failed",
            operation="health.readiness",
            status="failed",
            reason_code="dependency_error",
            dependency=dependency_name,
            exc_info=True,
        )
        return _dependency_readiness_result(
            service_name=service_name,
            dependency_name=dependency_name,
            status_value=READINESS_ERROR,
            started_at=started_at,
        )

    status_value = READINESS_OK if is_ready else READINESS_UNAVAILABLE
    return _dependency_readiness_result(
        service_name=service_name,
        dependency_name=dependency_name,
        status_value=status_value,
        started_at=started_at,
    )


def _coerce_dependency_result(
    dependency_name: str,
    result: DependencyReadinessResult | BaseException,
    *,
    service_name: str,
) -> DependencyReadinessResult:
    if isinstance(result, DependencyReadinessResult):
        return result
    log_operation_event(
        logger,
        logging.ERROR,
        "Health readiness isolation failed.",
        event_name="health.readiness_isolation.failed",
        operation="health.readiness",
        status="failed",
        reason_code="dependency_isolation_error",
        dependency=dependency_name,
        exc_info=(type(result), result, result.__traceback__),
    )
    observe_health_dependency_check(
        service=service_name,
        dependency=dependency_name,
        status=READINESS_ERROR,
        duration_seconds=0.0,
    )
    return DependencyReadinessResult(dependency_name, READINESS_ERROR)


def create_health_router(
    *dependencies: str,
    service_name: str = "lotus-core-service",
    readiness_cache_ttl_seconds: float = 5.0,
    readiness_dependency_timeout_seconds: float = 5.0,
) -> APIRouter:
    """
    Creates a standardized health check router.

    Args:
        *dependencies: A list of strings ('db', 'kafka') specifying which
                       dependencies to check for the readiness probe.
        service_name: Stable low-cardinality service label for health metrics.
        readiness_cache_ttl_seconds: Per-process cache duration for dependency
                       readiness results. Keeps probe storms from repeatedly
                       forcing expensive dependency metadata checks.
        readiness_dependency_timeout_seconds: Per-dependency timeout budget for
                       readiness checks. Keeps one slow dependency from hanging
                       the whole readiness response.

    Returns:
        A FastAPI APIRouter with /live and /ready endpoints.
    """
    router = APIRouter(tags=["Health"])

    dep_map = {
        "db": ("database", check_db_health, _database_dependency_configured),
        "kafka": ("kafka", check_kafka_health, _kafka_dependency_configured),
    }
    readiness_cache_ttl_seconds = max(0.0, readiness_cache_ttl_seconds)
    readiness_dependency_timeout_seconds = max(0.001, readiness_dependency_timeout_seconds)
    cached_until = 0.0
    cached_all_ok = False
    cached_dep_status: dict[str, str] | None = None

    @router.get(
        "/health/live",
        status_code=status.HTTP_200_OK,
        response_model=LiveHealthResponse,
        summary="Liveness probe",
        description="Return process liveness for the service runtime.",
        responses={
            200: {
                "description": "Service process is alive.",
                "content": {"application/json": {"example": {"status": "alive"}}},
            }
        },
    )
    async def liveness_probe():
        return {"status": "alive"}

    @router.get(
        "/health/ready",
        status_code=status.HTTP_200_OK,
        response_model=ReadyHealthResponse,
        summary="Readiness probe",
        description="Return dependency-aware readiness for the service runtime.",
        responses={
            200: {
                "description": "Service and required dependencies are ready.",
                "content": {
                    "application/json": {
                        "example": {"status": "ready", "dependencies": {"database": "ok"}}
                    }
                },
            },
            503: {
                "description": "One or more required dependencies are unavailable.",
                "content": {
                    "application/json": {
                        "example": {
                            "detail": {
                                "status": "not_ready",
                                "dependencies": {"database": "ok", "kafka": "timeout"},
                            }
                        }
                    }
                },
            },
        },
    )
    async def readiness_probe():
        nonlocal cached_all_ok, cached_dep_status, cached_until

        resolved_dependencies = [
            (dep_map[dep][0], dep_map[dep][1], dep_map[dep][2])
            for dep in dependencies
            if dep in dep_map
        ]
        now = time.monotonic()
        if readiness_cache_ttl_seconds > 0 and cached_dep_status is not None and now < cached_until:
            all_ok = cached_all_ok
            dep_status = dict(cached_dep_status)
        else:
            raw_results = await asyncio.gather(
                *[
                    _run_dependency_check(
                        dependency_name,
                        check,
                        configuration_check=configuration_check,
                        service_name=service_name,
                        timeout_seconds=readiness_dependency_timeout_seconds,
                    )
                    for dependency_name, check, configuration_check in resolved_dependencies
                ],
                return_exceptions=True,
            )
            results = [
                _coerce_dependency_result(
                    dependency_name,
                    result,
                    service_name=service_name,
                )
                for (dependency_name, _, _), result in zip(resolved_dependencies, raw_results)
            ]

            all_ok = all(result.is_ready for result in results)

            dep_status = {result.dependency_name: result.status for result in results}
            if readiness_cache_ttl_seconds > 0:
                cached_all_ok = all_ok
                cached_dep_status = dict(dep_status)
                cached_until = time.monotonic() + readiness_cache_ttl_seconds

        set_health_readiness_state(
            service=service_name,
            state="ready" if all_ok else "not_ready",
        )

        if all_ok:
            return {"status": "ready", "dependencies": dep_status}

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "dependencies": dep_status},
        )

    return router
