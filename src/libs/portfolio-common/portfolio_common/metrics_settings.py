from __future__ import annotations

import os
from dataclasses import dataclass

from portfolio_common.logging_utils import normalize_lineage_value

_METRICS_ACCESS_ENV_PREFIX = "LOTUS_METRICS_ACCESS"
METRICS_ACCESS_TOKEN_ENV = f"{_METRICS_ACCESS_ENV_PREFIX}_TOKEN"


@dataclass(frozen=True)
class MetricsRuntimeSettings:
    metrics_access_token: str | None = None


def load_metrics_runtime_settings() -> MetricsRuntimeSettings:
    return MetricsRuntimeSettings(
        metrics_access_token=normalize_lineage_value(os.getenv(METRICS_ACCESS_TOKEN_ENV))
    )
