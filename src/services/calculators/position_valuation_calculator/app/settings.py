"""Load strict runtime settings for position valuation workers."""

from __future__ import annotations

from dataclasses import dataclass

from portfolio_common.runtime_settings import env_int

SERVICE_NAME = "position valuation worker service"


@dataclass(frozen=True, slots=True)
class PositionValuationRuntimeSettings:
    """Configure bounded in-process valuation worker concurrency."""

    worker_count: int


def get_position_valuation_runtime_settings() -> PositionValuationRuntimeSettings:
    """Return validated valuation worker settings from the environment."""

    return PositionValuationRuntimeSettings(
        worker_count=int(
            env_int(
                "POSITION_VALUATION_WORKER_COUNT",
                1,
                service_name=SERVICE_NAME,
                minimum=1,
                minimum_fallback=1,
            )
        )
    )
