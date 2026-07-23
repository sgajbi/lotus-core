from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from sqlalchemy.engine import URL, Engine, make_url

from tests.test_support.runtime_env import PreparedTestRuntime

_DATABASE_CLEANUP_AUTHORITY = object()


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
        url = value if isinstance(value, URL) else make_url(str(value))
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


@dataclass(frozen=True)
class DatabaseCleanupAuthorization:
    """Capability proving one exact engine belongs to a prepared isolated test runtime."""

    compose_project_name: str
    target: DatabaseTargetIdentity
    _authority: object = field(repr=False, compare=False)


def authorize_database_cleanup(
    *,
    runtime: PreparedTestRuntime,
    engine: Engine,
) -> DatabaseCleanupAuthorization:
    """Fail closed unless the harness generated and owns the exact cleanup target."""

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

    expected = DatabaseTargetIdentity.from_url(runtime.endpoints.host_database_url)
    actual = DatabaseTargetIdentity.from_url(engine.url)
    if actual != expected:
        raise DatabaseCleanupAuthorizationError(
            "database cleanup refused: engine target does not match prepared test runtime "
            f"(expected={expected.diagnostic()}, actual={actual.diagnostic()})"
        )
    return DatabaseCleanupAuthorization(
        compose_project_name=runtime.endpoints.compose_project_name,
        target=expected,
        _authority=_DATABASE_CLEANUP_AUTHORITY,
    )


def require_database_cleanup_authorization(
    authorization: DatabaseCleanupAuthorization,
    *,
    engine: Engine,
) -> None:
    """Revalidate a cleanup capability before a delegated destructive helper runs."""

    if authorization._authority is not _DATABASE_CLEANUP_AUTHORITY:
        raise DatabaseCleanupAuthorizationError(
            "database cleanup refused: invalid cleanup authorization"
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
