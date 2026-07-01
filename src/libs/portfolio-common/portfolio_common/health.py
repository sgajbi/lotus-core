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
from .monitoring import observe_health_dependency_check, set_health_readiness_state

logger = logging.getLogger(__name__)

DependencyCheck = Callable[[], Awaitable[bool]]

READINESS_OK = "ok"
READINESS_UNAVAILABLE = "unavailable"
READINESS_TIMEOUT = "timeout"
READINESS_ERROR = "error"


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
    except Exception as e:
        logger.error(f"Health Check: Database connection failed: {e}", exc_info=False)
        return False


async def check_kafka_health() -> bool:
    """Checks if a connection can be established with Kafka."""
    try:
        admin_client = AdminClient({"bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS})
        await asyncio.to_thread(admin_client.list_topics, timeout=5)
        return True
    except Exception as e:
        logger.error(f"Health Check: Kafka connection failed: {e}", exc_info=False)
        return False


async def _run_dependency_check(
    dependency_name: str,
    check: DependencyCheck,
    *,
    service_name: str,
    timeout_seconds: float,
) -> DependencyReadinessResult:
    started_at = time.perf_counter()
    try:
        is_ready = await asyncio.wait_for(check(), timeout=timeout_seconds)
    except TimeoutError:
        logger.warning(
            "Health Check: %s readiness check timed out after %.2f seconds.",
            dependency_name,
            timeout_seconds,
        )
        observe_health_dependency_check(
            service=service_name,
            dependency=dependency_name,
            status=READINESS_TIMEOUT,
            duration_seconds=time.perf_counter() - started_at,
        )
        return DependencyReadinessResult(dependency_name, READINESS_TIMEOUT)
    except Exception:
        logger.exception("Health Check: %s readiness check failed.", dependency_name)
        observe_health_dependency_check(
            service=service_name,
            dependency=dependency_name,
            status=READINESS_ERROR,
            duration_seconds=time.perf_counter() - started_at,
        )
        return DependencyReadinessResult(dependency_name, READINESS_ERROR)

    status_value = READINESS_OK if is_ready else READINESS_UNAVAILABLE
    observe_health_dependency_check(
        service=service_name,
        dependency=dependency_name,
        status=status_value,
        duration_seconds=time.perf_counter() - started_at,
    )
    return DependencyReadinessResult(dependency_name, status_value)


def _coerce_dependency_result(
    dependency_name: str,
    result: DependencyReadinessResult | BaseException,
    *,
    service_name: str,
) -> DependencyReadinessResult:
    if isinstance(result, DependencyReadinessResult):
        return result
    logger.error(
        "Health Check: %s readiness isolation failed.",
        dependency_name,
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

    dep_map = {"db": ("database", check_db_health), "kafka": ("kafka", check_kafka_health)}
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
            (dep_map[dep][0], dep_map[dep][1]) for dep in dependencies if dep in dep_map
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
                        service_name=service_name,
                        timeout_seconds=readiness_dependency_timeout_seconds,
                    )
                    for dependency_name, check in resolved_dependencies
                ],
                return_exceptions=True,
            )
            results = [
                _coerce_dependency_result(
                    dependency_name,
                    result,
                    service_name=service_name,
                )
                for (dependency_name, _), result in zip(resolved_dependencies, raw_results)
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
