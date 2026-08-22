"""Bounded runtime identity for database connection attribution."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from .runtime_settings import (
    RuntimeConfigurationError,
    env_optional_str,
    strict_config_validation_enabled,
)

DATABASE_APPLICATION_NAME_MAX_LENGTH = 63
DATABASE_RUNTIME_IDENTITY_ENV = "SERVICE_NAME"
LOCAL_DATABASE_RUNTIME_IDENTITY = "lotus-core-local"
_database_runtime_identity_override: ContextVar[str | None] = ContextVar(
    "database_runtime_identity_override", default=None
)

# Keep this inventory bounded to deployed Core runtimes. Never add request, worker,
# pod, transaction, portfolio, or security identifiers to database application names.
DATABASE_RUNTIME_IDENTITIES = frozenset(
    {
        "derived-state-resource-monitor",
        "average-cost-reconciliation",
        "bank-day-reconciliation-report",
        "database-partition-advisor",
        "database-retention-maintenance",
        "derived-state-poison-gate",
        "derived-state-recovery-gate",
        "event-replay-service",
        "failure-recovery-gate",
        "financial-reconciliation-service",
        "ingestion-service",
        LOCAL_DATABASE_RUNTIME_IDENTITY,
        "lotus-core-test",
        "lot-position-parity-audit",
        "migration-runner",
        "offline-integrity-auditor",
        "performance-load-gate",
        "persistence-service",
        "portfolio-derived-state",
        "portfolio-transaction-processing",
        "position-valuation-calculator",
        "postgres-healthcheck",
        "query-control-plane-service",
        "query-service",
        "reprocess-transactions",
        "transaction-release-runtime",
        "valuation-orchestrator",
    }
)
NON_CERTIFYING_DATABASE_RUNTIME_IDENTITIES = frozenset(
    {LOCAL_DATABASE_RUNTIME_IDENTITY, "lotus-core-test"}
)


def _validate_database_runtime_identity(identity: str) -> str:
    normalized_identity = identity.strip()
    if not normalized_identity:
        raise RuntimeConfigurationError("Invalid database runtime identity: SERVICE_NAME is blank")
    if len(normalized_identity.encode("utf-8")) > DATABASE_APPLICATION_NAME_MAX_LENGTH:
        raise RuntimeConfigurationError(
            "Invalid database runtime identity: SERVICE_NAME exceeds PostgreSQL's 63-byte limit"
        )
    if normalized_identity not in DATABASE_RUNTIME_IDENTITIES:
        raise RuntimeConfigurationError(
            "Invalid database runtime identity: "
            f"SERVICE_NAME {normalized_identity!r} is not allowlisted"
        )
    return normalized_identity


def database_runtime_identity(*, explicit_identity: str | None = None) -> str:
    """Return the governed, low-cardinality PostgreSQL application identity."""

    configured_identity = (
        explicit_identity
        if explicit_identity is not None
        else (
            _database_runtime_identity_override.get()
            or env_optional_str(DATABASE_RUNTIME_IDENTITY_ENV)
        )
    )
    if configured_identity is None:
        if strict_config_validation_enabled():
            raise RuntimeConfigurationError(
                "Missing database runtime identity: SERVICE_NAME is required outside local/test "
                "environments"
            )
        return LOCAL_DATABASE_RUNTIME_IDENTITY

    return _validate_database_runtime_identity(configured_identity)


@contextmanager
def database_runtime_identity_scope(identity: str) -> Iterator[None]:
    """Apply one validated process-tool identity to lazily created shared engines."""

    validated_identity = _validate_database_runtime_identity(identity)
    token = _database_runtime_identity_override.set(validated_identity)
    try:
        yield
    finally:
        _database_runtime_identity_override.reset(token)
