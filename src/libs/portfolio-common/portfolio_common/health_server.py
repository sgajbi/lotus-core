"""Shared health-probe server runtime configuration."""

from __future__ import annotations

from portfolio_common import config

HEALTH_PROBE_BIND_HOST_ENV = config.HEALTH_PROBE_BIND_HOST_ENV

def health_probe_bind_host() -> str:
    return config.load_health_probe_bind_host()
