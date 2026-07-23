from __future__ import annotations

import time
import weakref
from dataclasses import dataclass, field
from typing import Callable

from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.exc import ArgumentError

from tests.test_support.runtime_env import PreparedTestRuntime

_DATABASE_CLEANUP_ISSUANCE_TOKEN = object()


class DatabaseCleanupAuthorizationError(RuntimeError):
    """Raised before destructive test cleanup when target ownership is unproven."""


@dataclass(frozen=True)
class DatabaseTargetIdentity:
    """Credential-free PostgreSQL target identity used for exact ownership checks."""

    username: str
    host: str
    port: int
    database: str

    @classmethod
    def from_url(cls, value: URL | str) -> DatabaseTargetIdentity:
        try:
            url = value if isinstance(value, URL) else make_url(str(value))
        except ArgumentError as exc:
            raise DatabaseCleanupAuthorizationError(
                "database cleanup refused: PostgreSQL target URL is invalid"
            ) from exc
        if url.get_backend_name() != "postgresql":
            raise DatabaseCleanupAuthorizationError(
                "database cleanup refused: target backend must be PostgreSQL"
            )
        if url.query:
            raise DatabaseCleanupAuthorizationError(
                "database cleanup refused: PostgreSQL target query parameters are not allowed"
            )
        if not url.username or not url.host or url.port is None or not url.database:
            raise DatabaseCleanupAuthorizationError(
                "database cleanup refused: PostgreSQL target must declare user, host, port, "
                "and database"
            )
        return cls(
            username=url.username,
            host=url.host.lower(),
            port=url.port,
            database=url.database,
        )

    def diagnostic(self) -> str:
        """Render a credential-free target for actionable failure diagnostics."""

        return f"{self.username}@{self.host}:{self.port}/{self.database}"


@dataclass(frozen=True, init=False)
class DatabaseCleanupAuthorization:
    """Capability proving one exact engine belongs to a prepared isolated test runtime."""

    compose_project_name: str
    target: DatabaseTargetIdentity
    reservation_generation: int
    _runtime_ref: weakref.ReferenceType[PreparedTestRuntime] = field(
        repr=False,
        compare=False,
    )

    def __init__(
        self,
        *,
        compose_project_name: str,
        target: DatabaseTargetIdentity,
        _issuance_token: object,
        runtime: PreparedTestRuntime | None = None,
        reservation_generation: int | None = None,
    ) -> None:
        if _issuance_token is not _DATABASE_CLEANUP_ISSUANCE_TOKEN:
            raise TypeError("database cleanup authorizations are factory-issued")
        if runtime is None or reservation_generation is None:
            raise TypeError("database cleanup authorization issuance context is required")
        object.__setattr__(self, "compose_project_name", compose_project_name)
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "reservation_generation", reservation_generation)
        object.__setattr__(self, "_runtime_ref", weakref.ref(runtime))


_ISSUED_DATABASE_CLEANUP_AUTHORIZATIONS: weakref.WeakValueDictionary[
    int, DatabaseCleanupAuthorization
] = weakref.WeakValueDictionary()


def _issue_database_cleanup_authorization(
    *,
    runtime: PreparedTestRuntime,
    compose_project_name: str,
    target: DatabaseTargetIdentity,
    reservation_generation: int,
) -> DatabaseCleanupAuthorization:
    authorization = DatabaseCleanupAuthorization(
        compose_project_name=compose_project_name,
        target=target,
        runtime=runtime,
        reservation_generation=reservation_generation,
        _issuance_token=_DATABASE_CLEANUP_ISSUANCE_TOKEN,
    )
    _ISSUED_DATABASE_CLEANUP_AUTHORIZATIONS[id(authorization)] = authorization
    return authorization


def _owned_database_cleanup_target(
    runtime: PreparedTestRuntime,
) -> tuple[DatabaseTargetIdentity, int, str]:
    """Revalidate current runtime provenance and return its exact cleanup target."""

    if not runtime.prepared_by_current_process:
        raise DatabaseCleanupAuthorizationError(
            "database cleanup refused: runtime lacks current-process preparation provenance"
        )
    if not runtime.compose_project_generated:
        raise DatabaseCleanupAuthorizationError(
            "database cleanup refused: Compose project identity was inherited"
        )
    if not runtime.postgres_host_port_reserved:
        raise DatabaseCleanupAuthorizationError(
            "database cleanup refused: PostgreSQL host port was not dynamically reserved "
            "by this test runtime"
        )

    prepared = runtime.prepared_database_target
    if prepared.reservation_generation != runtime.port_reservation.generation:
        raise DatabaseCleanupAuthorizationError(
            "database cleanup refused: prepared target generation is stale"
        )
    expected = DatabaseTargetIdentity(
        username=prepared.username,
        host=prepared.host,
        port=prepared.port,
        database=prepared.database,
    )
    current_project = runtime.values.get("COMPOSE_PROJECT_NAME")
    if current_project != prepared.compose_project_name:
        raise DatabaseCleanupAuthorizationError(
            "database cleanup refused: Compose project identity changed after preparation"
        )
    current_components = (
        runtime.values.get("POSTGRES_USER"),
        runtime.values.get("LOTUS_POSTGRES_HOST_PORT"),
        runtime.values.get("POSTGRES_DB"),
    )
    prepared_components = (
        prepared.username,
        str(prepared.port),
        prepared.database,
    )
    if current_components != prepared_components:
        raise DatabaseCleanupAuthorizationError(
            "database cleanup refused: PostgreSQL target components changed after preparation"
        )
    current_derived_target = DatabaseTargetIdentity.from_url(
        runtime.values.get("HOST_DATABASE_URL", "")
    )
    if current_derived_target != expected:
        raise DatabaseCleanupAuthorizationError(
            "database cleanup refused: derived database endpoint changed after preparation "
            f"(prepared={expected.diagnostic()}, "
            f"current={current_derived_target.diagnostic()})"
        )
    return expected, prepared.reservation_generation, prepared.compose_project_name


def authorize_database_cleanup(
    *,
    runtime: PreparedTestRuntime,
    engine: Engine,
) -> DatabaseCleanupAuthorization:
    """Fail closed unless the harness generated and owns the exact cleanup target."""

    expected, reservation_generation, compose_project_name = _owned_database_cleanup_target(runtime)
    actual = DatabaseTargetIdentity.from_url(engine.url)
    if actual != expected:
        raise DatabaseCleanupAuthorizationError(
            "database cleanup refused: engine target does not match prepared test runtime "
            f"(expected={expected.diagnostic()}, actual={actual.diagnostic()})"
        )
    return _issue_database_cleanup_authorization(
        runtime=runtime,
        compose_project_name=compose_project_name,
        target=expected,
        reservation_generation=reservation_generation,
    )


def require_database_cleanup_authorization(
    authorization: DatabaseCleanupAuthorization,
    *,
    engine: Engine,
) -> None:
    """Revalidate a cleanup capability before a delegated destructive helper runs."""

    if _ISSUED_DATABASE_CLEANUP_AUTHORIZATIONS.get(id(authorization)) is not authorization:
        raise DatabaseCleanupAuthorizationError(
            "database cleanup refused: invalid cleanup authorization"
        )
    runtime = authorization._runtime_ref()
    if runtime is None:
        raise DatabaseCleanupAuthorizationError(
            "database cleanup refused: originating test runtime is no longer available"
        )
    current_target, current_generation, current_project = _owned_database_cleanup_target(runtime)
    if (
        authorization.compose_project_name != current_project
        or authorization.reservation_generation != current_generation
        or authorization.target != current_target
    ):
        raise DatabaseCleanupAuthorizationError(
            "database cleanup refused: cleanup authorization is stale for the current "
            "runtime generation or target"
        )
    actual = DatabaseTargetIdentity.from_url(engine.url)
    if actual != authorization.target:
        raise DatabaseCleanupAuthorizationError(
            "database cleanup refused: delegated engine target differs from authorization "
            f"(expected={authorization.target.diagnostic()}, actual={actual.diagnostic()})"
        )


def truncate_with_deadlock_retry(
    executor: Callable[[], None],
    *,
    max_attempts: int = 5,
    backoff_seconds: float = 0.25,
    on_deadlock_retry: Callable[[], None] | None = None,
) -> None:
    """Retry cleanup if PostgreSQL reports transient deadlock."""
    attempts = max(1, max_attempts)
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            executor()
            return
        except Exception as exc:  # pragma: no cover - generic by design
            last_error = exc
            if "deadlock detected" not in str(exc).lower() or attempt == attempts:
                raise
            if on_deadlock_retry is not None:
                on_deadlock_retry()
            time.sleep(backoff_seconds * attempt)

    if last_error:
        raise last_error
