from __future__ import annotations

import time
from typing import Callable


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
