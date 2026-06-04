"""Shared health-probe server runtime configuration."""

from __future__ import annotations

from portfolio_common.config import (
    HEALTH_PROBE_BIND_HOST_ENV,
    load_health_probe_bind_host,
)


def health_probe_bind_host() -> str:
    return load_health_probe_bind_host()
