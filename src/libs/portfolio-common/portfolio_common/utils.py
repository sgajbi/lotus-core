# libs/portfolio-common/portfolio_common/utils.py
import functools
import time
from typing import Any, Callable

from .monitoring import DB_OPERATION_LATENCY_SECONDS


def async_timed(repository: str, method: str) -> Callable:
    """
    A decorator that times an async function and records the latency
    in the DB_OPERATION_LATENCY_SECONDS Prometheus histogram.

    Args:
        repository: The name of the repository class (e.g., 'TransactionRepository').
        method: The name of the method being timed (e.g., 'get_transactions').
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            start_time = time.monotonic()
            try:
                return await func(*args, **kwargs)
            finally:
                end_time = time.monotonic()
                duration = end_time - start_time
                DB_OPERATION_LATENCY_SECONDS.labels(
                    repository=repository,
                    method=method
                ).observe(duration)
        return wrapper
    return decorator