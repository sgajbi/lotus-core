# src/libs/portfolio-common/portfolio_common/health.py
import asyncio
import logging
from typing import Awaitable, Callable

from confluent_kafka.admin import AdminClient
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from .config import KAFKA_BOOTSTRAP_SERVERS
from .db import AsyncSessionLocal

logger = logging.getLogger(__name__)

DependencyCheck = Callable[[], Awaitable[bool]]


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
        examples=[{"database": "ok", "kafka": "unavailable"}],
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


def create_health_router(*dependencies: str) -> APIRouter:
    """
    Creates a standardized health check router.

    Args:
        *dependencies: A list of strings ('db', 'kafka') specifying which
                       dependencies to check for the readiness probe.

    Returns:
        A FastAPI APIRouter with /live and /ready endpoints.
    """
    router = APIRouter(tags=["Health"])

    dep_map = {"db": ("database", check_db_health), "kafka": ("kafka", check_kafka_health)}

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
                                "dependencies": {"database": "ok", "kafka": "unavailable"},
                            }
                        }
                    }
                },
            },
        },
    )
    async def readiness_probe():
        checks_to_run = [dep_map[dep][1] for dep in dependencies if dep in dep_map]

        results = await asyncio.gather(*[check() for check in checks_to_run])

        all_ok = all(results)

        dep_status = {
            dep_map[dep][0]: "ok" if results[i] else "unavailable"
            for i, dep in enumerate(dependencies)
            if dep in dep_map
        }

        if all_ok:
            return {"status": "ready", "dependencies": dep_status}

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "dependencies": dep_status},
        )

    return router
