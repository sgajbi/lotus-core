"""Bounded runtime identity for database connection attribution."""

from __future__ import annotations

import os

from .runtime_settings import RuntimeConfigurationError, strict_config_validation_enabled

DATABASE_APPLICATION_NAME_MAX_LENGTH = 63
DATABASE_RUNTIME_IDENTITY_ENV = "SERVICE_NAME"
LOCAL_DATABASE_RUNTIME_IDENTITY = "lotus-core-local"

# Keep this inventory bounded to deployed Core runtimes. Never add request, worker,
# pod, transaction, portfolio, or security identifiers to database application names.
DATABASE_RUNTIME_IDENTITIES = frozenset(
    {
        "derived-state-resource-monitor",
        "event-replay-service",
        "financial-reconciliation-service",
        "ingestion-service",
        LOCAL_DATABASE_RUNTIME_IDENTITY,
        "lotus-core-test",
        "migration-runner",
        "persistence-service",
        "portfolio-derived-state",
        "portfolio-transaction-processing",
        "position-valuation-calculator",
        "postgres-healthcheck",
        "query-control-plane-service",
        "query-service",
        "valuation-orchestrator",
    }
)
NON_CERTIFYING_DATABASE_RUNTIME_IDENTITIES = frozenset(
    {LOCAL_DATABASE_RUNTIME_IDENTITY, "lotus-core-test"}
)


def database_runtime_identity() -> str:
    """Return the governed, low-cardinality PostgreSQL application identity."""

    configured_identity = os.getenv(DATABASE_RUNTIME_IDENTITY_ENV)
    if configured_identity is None:
        if strict_config_validation_enabled():
            raise RuntimeConfigurationError(
                "Missing database runtime identity: SERVICE_NAME is required outside local/test "
                "environments"
            )
        return LOCAL_DATABASE_RUNTIME_IDENTITY

    identity = configured_identity.strip()
    if not identity:
        raise RuntimeConfigurationError("Invalid database runtime identity: SERVICE_NAME is blank")
    if len(identity.encode("utf-8")) > DATABASE_APPLICATION_NAME_MAX_LENGTH:
        raise RuntimeConfigurationError(
            "Invalid database runtime identity: SERVICE_NAME exceeds PostgreSQL's 63-byte limit"
        )
    if identity not in DATABASE_RUNTIME_IDENTITIES:
        raise RuntimeConfigurationError(
            f"Invalid database runtime identity: SERVICE_NAME {identity!r} is not allowlisted"
        )
    return identity


def sync_database_connect_args() -> dict[str, str]:
    """Build psycopg connection metadata from the governed runtime identity."""

    return {"application_name": database_runtime_identity()}


def async_database_connect_args() -> dict[str, dict[str, str]]:
    """Build asyncpg connection metadata from the governed runtime identity."""

    return {"server_settings": {"application_name": database_runtime_identity()}}
