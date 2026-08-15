"""Governed database pool and server-timeout settings for Core runtimes."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.pool import NullPool

from .database_runtime_identity import DATABASE_RUNTIME_IDENTITIES, database_runtime_identity
from .runtime_settings import RuntimeConfigurationError, env_optional_str

logger = logging.getLogger(__name__)

DATABASE_POOL_SIZE_ENV = "LOTUS_CORE_DB_POOL_SIZE"
DATABASE_MAX_OVERFLOW_ENV = "LOTUS_CORE_DB_MAX_OVERFLOW"
DATABASE_POOL_TIMEOUT_SECONDS_ENV = "LOTUS_CORE_DB_POOL_TIMEOUT_SECONDS"
DATABASE_POOL_RECYCLE_SECONDS_ENV = "LOTUS_CORE_DB_POOL_RECYCLE_SECONDS"
DATABASE_CONNECT_TIMEOUT_SECONDS_ENV = "LOTUS_CORE_DB_CONNECT_TIMEOUT_SECONDS"
DATABASE_STATEMENT_TIMEOUT_MS_ENV = "LOTUS_CORE_DB_STATEMENT_TIMEOUT_MS"
DATABASE_IDLE_TRANSACTION_TIMEOUT_MS_ENV = "LOTUS_CORE_DB_IDLE_IN_TRANSACTION_SESSION_TIMEOUT_MS"


class DatabasePoolMode(StrEnum):
    QUEUE = "queue"
    NULL = "null"


class DatabaseRuntimeCohort(StrEnum):
    HTTP = "online-http"
    STREAM = "online-stream"
    SCHEDULER = "online-scheduler"
    MIGRATION = "migration-nullpool"
    OPERATOR = "operator"
    TEST = "test-nullpool"


class DatabaseRuntimeProfileError(RuntimeConfigurationError):
    """Reject an invalid database profile without disclosing its raw value."""

    def __init__(self, *, setting: str, reason: str) -> None:
        self.setting = setting
        self.reason = reason
        super().__init__(f"Invalid database runtime profile setting {setting}: {reason}")


_HTTP_IDENTITIES = {
    "ingestion-service",
    "query-service",
    "query-control-plane-service",
    "event-replay-service",
}
_STREAM_IDENTITIES = {
    "financial-reconciliation-service",
    "persistence-service",
    "portfolio-transaction-processing",
    "position-valuation-calculator",
    "portfolio-derived-state",
}
_SCHEDULER_IDENTITIES = {"valuation-orchestrator"}
_MIGRATION_IDENTITIES = {"migration-runner"}
_TEST_IDENTITIES = {"lotus-core-test", "lotus-core-local"}

DATABASE_RUNTIME_COHORT_BY_IDENTITY = {
    identity: (
        DatabaseRuntimeCohort.HTTP
        if identity in _HTTP_IDENTITIES
        else DatabaseRuntimeCohort.STREAM
        if identity in _STREAM_IDENTITIES
        else DatabaseRuntimeCohort.SCHEDULER
        if identity in _SCHEDULER_IDENTITIES
        else DatabaseRuntimeCohort.MIGRATION
        if identity in _MIGRATION_IDENTITIES
        else DatabaseRuntimeCohort.TEST
        if identity in _TEST_IDENTITIES
        else DatabaseRuntimeCohort.OPERATOR
    )
    for identity in DATABASE_RUNTIME_IDENTITIES
}


@dataclass(frozen=True, slots=True)
class DatabaseRuntimeProfile:
    runtime_identity: str
    cohort: DatabaseRuntimeCohort
    pool_mode: DatabasePoolMode
    pool_size: int | None
    max_overflow: int | None
    pool_timeout_seconds: int | None
    pool_recycle_seconds: int | None
    connect_timeout_seconds: int
    statement_timeout_ms: int
    idle_in_transaction_session_timeout_ms: int

    @property
    def maximum_connections_per_process(self) -> int | None:
        if self.pool_size is None or self.max_overflow is None:
            return None
        return self.pool_size + self.max_overflow


def _bounded_integer(
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
    disabled_value: int | None = None,
) -> int:
    raw = env_optional_str(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise DatabaseRuntimeProfileError(setting=name, reason="expected an integer") from exc
    if disabled_value is not None and value == disabled_value:
        return value
    if not minimum <= value <= maximum:
        raise DatabaseRuntimeProfileError(
            setting=name,
            reason=f"expected a value between {minimum} and {maximum}",
        )
    return value


def database_runtime_profile(
    *,
    explicit_identity: str | None = None,
    pool_mode: DatabasePoolMode = DatabasePoolMode.QUEUE,
) -> DatabaseRuntimeProfile:
    """Load and validate the non-secret database profile before engine creation."""

    identity = database_runtime_identity(explicit_identity=explicit_identity)
    pool_size = (
        _bounded_integer(DATABASE_POOL_SIZE_ENV, 5, minimum=1, maximum=32)
        if pool_mode is DatabasePoolMode.QUEUE
        else None
    )
    max_overflow = (
        _bounded_integer(DATABASE_MAX_OVERFLOW_ENV, 10, minimum=0, maximum=32)
        if pool_mode is DatabasePoolMode.QUEUE
        else None
    )
    if pool_size is not None and max_overflow is not None and pool_size + max_overflow > 32:
        raise DatabaseRuntimeProfileError(
            setting=f"{DATABASE_POOL_SIZE_ENV}+{DATABASE_MAX_OVERFLOW_ENV}",
            reason="combined connection capacity must not exceed 32",
        )

    return DatabaseRuntimeProfile(
        runtime_identity=identity,
        cohort=DATABASE_RUNTIME_COHORT_BY_IDENTITY[identity],
        pool_mode=pool_mode,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout_seconds=(
            _bounded_integer(
                DATABASE_POOL_TIMEOUT_SECONDS_ENV,
                30,
                minimum=1,
                maximum=300,
            )
            if pool_mode is DatabasePoolMode.QUEUE
            else None
        ),
        pool_recycle_seconds=(
            _bounded_integer(
                DATABASE_POOL_RECYCLE_SECONDS_ENV,
                -1,
                minimum=60,
                maximum=86_400,
                disabled_value=-1,
            )
            if pool_mode is DatabasePoolMode.QUEUE
            else None
        ),
        connect_timeout_seconds=_bounded_integer(
            DATABASE_CONNECT_TIMEOUT_SECONDS_ENV,
            60,
            minimum=1,
            maximum=60,
        ),
        statement_timeout_ms=_bounded_integer(
            DATABASE_STATEMENT_TIMEOUT_MS_ENV,
            0,
            minimum=100,
            maximum=3_600_000,
            disabled_value=0,
        ),
        idle_in_transaction_session_timeout_ms=_bounded_integer(
            DATABASE_IDLE_TRANSACTION_TIMEOUT_MS_ENV,
            0,
            minimum=1_000,
            maximum=900_000,
            disabled_value=0,
        ),
    )


def sync_database_engine_options(profile: DatabaseRuntimeProfile) -> dict[str, object]:
    options: dict[str, object] = {
        "connect_args": {
            "application_name": profile.runtime_identity,
            "connect_timeout": profile.connect_timeout_seconds,
            "options": (
                f"-c statement_timeout={profile.statement_timeout_ms} "
                "-c idle_in_transaction_session_timeout="
                f"{profile.idle_in_transaction_session_timeout_ms}"
            ),
        }
    }
    return _with_pool_options(options, profile)


def async_database_engine_options(profile: DatabaseRuntimeProfile) -> dict[str, object]:
    options: dict[str, object] = {
        "connect_args": {
            "timeout": profile.connect_timeout_seconds,
            "server_settings": {
                "application_name": profile.runtime_identity,
                "statement_timeout": f"{profile.statement_timeout_ms}ms",
                "idle_in_transaction_session_timeout": (
                    f"{profile.idle_in_transaction_session_timeout_ms}ms"
                ),
            },
        }
    }
    return _with_pool_options(options, profile)


def _with_pool_options(
    options: dict[str, object], profile: DatabaseRuntimeProfile
) -> dict[str, object]:
    if profile.pool_mode is DatabasePoolMode.NULL:
        options["poolclass"] = NullPool
        return options
    options.update(
        {
            "pool_pre_ping": True,
            "pool_size": profile.pool_size,
            "max_overflow": profile.max_overflow,
            "pool_timeout": profile.pool_timeout_seconds,
            "pool_recycle": profile.pool_recycle_seconds,
        }
    )
    return options


def log_database_runtime_profile(profile: DatabaseRuntimeProfile, *, driver: str) -> None:
    """Publish bounded startup evidence without connection or business identifiers."""

    logger.info(
        "Validated database runtime profile.",
        extra={
            "runtime_identity": profile.runtime_identity,
            "database_runtime_cohort": profile.cohort.value,
            "database_driver": driver,
            "database_pool_mode": profile.pool_mode.value,
            "database_pool_size": profile.pool_size,
            "database_max_overflow": profile.max_overflow,
            "database_maximum_connections_per_process": (profile.maximum_connections_per_process),
            "database_pool_timeout_seconds": profile.pool_timeout_seconds,
            "database_pool_recycle_seconds": profile.pool_recycle_seconds,
            "database_connect_timeout_seconds": profile.connect_timeout_seconds,
            "database_statement_timeout_ms": profile.statement_timeout_ms,
            "database_idle_in_transaction_session_timeout_ms": (
                profile.idle_in_transaction_session_timeout_ms
            ),
        },
    )
