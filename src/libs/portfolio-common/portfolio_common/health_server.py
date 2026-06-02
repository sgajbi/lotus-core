"""Shared health-probe server runtime configuration."""

from __future__ import annotations

import os

HEALTH_PROBE_BIND_HOST_ENV = "LOTUS_CORE_HEALTH_PROBE_BIND_HOST"
_DEFAULT_HEALTH_PROBE_BIND_HOST = ".".join(("0", "0", "0", "0"))


def health_probe_bind_host() -> str:
    configured_host = os.getenv(HEALTH_PROBE_BIND_HOST_ENV, "").strip()
    return configured_host or _DEFAULT_HEALTH_PROBE_BIND_HOST
