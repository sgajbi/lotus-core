from __future__ import annotations

import json
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_decimal(name: str, default: str) -> Decimal:
    raw = os.getenv(name)
    if raw is None:
        return Decimal(default)
    try:
        return Decimal(raw)
    except Exception:
        return Decimal(default)


def _env_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    return default if raw is None else raw


@dataclass(frozen=True, slots=True)
class IngestionOpsAuthSettings:
    token_required: bool
    token_value: str
    auth_mode: Literal["token_or_jwt", "jwt_only", "token_only"]
    jwt_hs256_secret: str
    jwt_issuer: str
    jwt_audience: str
    jwt_clock_skew_seconds: int


@dataclass(frozen=True, slots=True)
class IngestionRateLimitSettings:
    enabled: bool
    window_seconds: int
    max_requests: int
    max_records: int


@dataclass(frozen=True, slots=True)
class IngestionOperatingBandSettings:
    yellow_backlog_age_seconds: float
    orange_backlog_age_seconds: float
    red_backlog_age_seconds: float
    yellow_dlq_pressure_ratio: Decimal
    orange_dlq_pressure_ratio: Decimal
    red_dlq_pressure_ratio: Decimal


@dataclass(frozen=True, slots=True)
class IngestionRuntimePolicySettings:
    replay_max_records_per_request: int
    replay_max_backlog_jobs: int
    dlq_budget_events_per_window: int
    default_lookback_minutes: int
    default_failure_rate_threshold: Decimal
    default_queue_latency_threshold_seconds: float
    default_backlog_age_threshold_seconds: float
    reprocessing_worker_poll_interval_seconds: int
    reprocessing_worker_batch_size: int
    valuation_scheduler_poll_interval_seconds: int
    valuation_scheduler_batch_size: int
    valuation_scheduler_dispatch_rounds: int
    capacity_assumed_replicas: int
    replay_isolation_mode: str
    partition_growth_strategy: str
    calculator_peak_lag_age_seconds: dict[str, int]
    operating_band: IngestionOperatingBandSettings


@dataclass(frozen=True, slots=True)
class IngestionServiceSettings:
    ops_auth: IngestionOpsAuthSettings
    rate_limit: IngestionRateLimitSettings
    runtime_policy: IngestionRuntimePolicySettings


def _load_calculator_peak_lag_age_seconds() -> dict[str, int]:
    defaults = {
        "position": 30,
        "cost": 45,
        "valuation": 60,
        "cashflow": 45,
        "timeseries": 120,
    }
    raw = os.getenv("LOTUS_CORE_CALCULATOR_PEAK_LAG_AGE_SECONDS_JSON")
    if not raw:
        return dict(defaults)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return dict(defaults)
    if not isinstance(parsed, dict):
        return dict(defaults)
    return {key: _env_int_from_mapping(parsed, key, default) for key, default in defaults.items()}


def _env_int_from_mapping(values: dict[str, object], key: str, default: int) -> int:
    raw = values.get(key)
    try:
        return int(raw) if raw is not None else default
    except (TypeError, ValueError):
        return default


def load_ingestion_service_settings() -> IngestionServiceSettings:
    raw_auth_mode = _env_str("LOTUS_CORE_INGEST_OPS_AUTH_MODE", "token_or_jwt")
    auth_mode: Literal["token_or_jwt", "jwt_only", "token_only"]
    if raw_auth_mode in {"token_or_jwt", "jwt_only", "token_only"}:
        auth_mode = raw_auth_mode
    else:
        auth_mode = "token_or_jwt"

    return IngestionServiceSettings(
        ops_auth=IngestionOpsAuthSettings(
            token_required=_env_bool("LOTUS_CORE_INGEST_OPS_TOKEN_REQUIRED", True),
            token_value=_env_str("LOTUS_CORE_INGEST_OPS_TOKEN", "lotus-core-ops-local"),
            auth_mode=auth_mode,
            jwt_hs256_secret=_env_str("LOTUS_CORE_INGEST_OPS_JWT_HS256_SECRET", ""),
            jwt_issuer=_env_str("LOTUS_CORE_INGEST_OPS_JWT_ISSUER", ""),
            jwt_audience=_env_str("LOTUS_CORE_INGEST_OPS_JWT_AUDIENCE", ""),
            jwt_clock_skew_seconds=_env_int("LOTUS_CORE_INGEST_OPS_JWT_CLOCK_SKEW_SECONDS", 60),
        ),
        rate_limit=IngestionRateLimitSettings(
            enabled=_env_bool("LOTUS_CORE_INGEST_RATE_LIMIT_ENABLED", True),
            window_seconds=_env_int("LOTUS_CORE_INGEST_RATE_LIMIT_WINDOW_SECONDS", 60),
            max_requests=_env_int("LOTUS_CORE_INGEST_RATE_LIMIT_MAX_REQUESTS", 120),
            max_records=_env_int("LOTUS_CORE_INGEST_RATE_LIMIT_MAX_RECORDS", 10000),
        ),
        runtime_policy=IngestionRuntimePolicySettings(
            replay_max_records_per_request=_env_int(
                "LOTUS_CORE_REPLAY_MAX_RECORDS_PER_REQUEST", 5000
            ),
            replay_max_backlog_jobs=_env_int("LOTUS_CORE_REPLAY_MAX_BACKLOG_JOBS", 5000),
            dlq_budget_events_per_window=_env_int(
                "LOTUS_CORE_DLQ_EVENTS_BUDGET_PER_WINDOW", 10
            ),
            default_lookback_minutes=_env_int("LOTUS_CORE_DEFAULT_LOOKBACK_MINUTES", 60),
            default_failure_rate_threshold=_env_decimal(
                "LOTUS_CORE_DEFAULT_FAILURE_RATE_THRESHOLD", "0.03"
            ),
            default_queue_latency_threshold_seconds=_env_float(
                "LOTUS_CORE_DEFAULT_QUEUE_LATENCY_THRESHOLD_SECONDS", 5.0
            ),
            default_backlog_age_threshold_seconds=_env_float(
                "LOTUS_CORE_DEFAULT_BACKLOG_AGE_THRESHOLD_SECONDS", 300.0
            ),
            reprocessing_worker_poll_interval_seconds=_env_int(
                "REPROCESSING_WORKER_POLL_INTERVAL_SECONDS", 10
            ),
            reprocessing_worker_batch_size=_env_int("REPROCESSING_WORKER_BATCH_SIZE", 10),
            valuation_scheduler_poll_interval_seconds=_env_int(
                "VALUATION_SCHEDULER_POLL_INTERVAL", 30
            ),
            valuation_scheduler_batch_size=_env_int("VALUATION_SCHEDULER_BATCH_SIZE", 100),
            valuation_scheduler_dispatch_rounds=_env_int(
                "VALUATION_SCHEDULER_DISPATCH_ROUNDS", 3
            ),
            capacity_assumed_replicas=_env_int("LOTUS_CORE_CAPACITY_ASSUMED_REPLICAS", 1),
            replay_isolation_mode=_env_str(
                "LOTUS_CORE_REPLAY_ISOLATION_MODE", "shared_workers"
            ),
            partition_growth_strategy=_env_str(
                "LOTUS_CORE_PARTITION_GROWTH_STRATEGY", "scale_out_only"
            ),
            calculator_peak_lag_age_seconds=_load_calculator_peak_lag_age_seconds(),
            operating_band=IngestionOperatingBandSettings(
                yellow_backlog_age_seconds=_env_float(
                    "LOTUS_CORE_OPERATING_BAND_YELLOW_BACKLOG_AGE_SECONDS", 15.0
                ),
                orange_backlog_age_seconds=_env_float(
                    "LOTUS_CORE_OPERATING_BAND_ORANGE_BACKLOG_AGE_SECONDS", 60.0
                ),
                red_backlog_age_seconds=_env_float(
                    "LOTUS_CORE_OPERATING_BAND_RED_BACKLOG_AGE_SECONDS", 180.0
                ),
                yellow_dlq_pressure_ratio=_env_decimal(
                    "LOTUS_CORE_OPERATING_BAND_YELLOW_DLQ_PRESSURE_RATIO", "0.25"
                ),
                orange_dlq_pressure_ratio=_env_decimal(
                    "LOTUS_CORE_OPERATING_BAND_ORANGE_DLQ_PRESSURE_RATIO", "0.50"
                ),
                red_dlq_pressure_ratio=_env_decimal(
                    "LOTUS_CORE_OPERATING_BAND_RED_DLQ_PRESSURE_RATIO", "1.0"
                ),
            ),
        ),
    )


_SETTINGS = load_ingestion_service_settings()


def get_ingestion_service_settings() -> IngestionServiceSettings:
    return _SETTINGS
