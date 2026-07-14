"""Shared instrumentation helpers with signature-preserving typing."""

from __future__ import annotations

import functools
import time
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

from .monitoring import DB_OPERATION_LATENCY_SECONDS

_P = ParamSpec("_P")
_ResultT = TypeVar("_ResultT")


def async_timed(
    repository: str,
    method: str,
) -> Callable[
    [Callable[_P, Awaitable[_ResultT]]],
    Callable[_P, Awaitable[_ResultT]],
]:
    """
    A decorator that times an async function and records the latency
    in the DB_OPERATION_LATENCY_SECONDS Prometheus histogram.

    Args:
        repository: The name of the repository class (e.g., 'TransactionRepository').
        method: The name of the method being timed (e.g., 'get_transactions').
    """

    def decorator(
        func: Callable[_P, Awaitable[_ResultT]],
    ) -> Callable[_P, Awaitable[_ResultT]]:
        @functools.wraps(func)
        async def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _ResultT:
            start_time = time.monotonic()
            try:
                return await func(*args, **kwargs)
            finally:
                duration = time.monotonic() - start_time
                DB_OPERATION_LATENCY_SECONDS.labels(repository=repository, method=method).observe(
                    duration
                )

        return wrapper

    return decorator
