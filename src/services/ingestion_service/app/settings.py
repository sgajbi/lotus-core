from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, cast

logger = logging.getLogger(__name__)

STRICT_CONFIG_VALIDATION_ENV = "LOTUS_CORE_STRICT_CONFIG_VALIDATION"
LOCAL_CONFIG_ENVIRONMENTS = {"", "local", "dev", "development", "test"}
TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}
FALSY_ENV_VALUES = {"0", "false", "no", "off"}

IngestionRateLimitEnforcementScope = Literal[
    "local_process",
    "upstream_gateway",
    "local_process_with_upstream_gateway",
]


class IngestionConfigurationError(ValueError):
    """Raised when strict ingestion configuration validation rejects an env value."""


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in TRUTHY_ENV_VALUES:
        return True
    if normalized in FALSY_ENV_VALUES:
        return False
    return bool(
        _invalid_env_setting(
            name=name,
            raw=raw,
            default=default,
            reason="expected boolean value",
        )
    )


def _env_int(
    name: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return int(
            _invalid_env_setting(
                name=name,
                raw=raw,
                default=default,
                reason="expected integer value",
            )
        )
    if minimum is not None and value < minimum:
        return int(
            _invalid_env_setting(
                name=name,
                raw=raw,
                default=default,
                reason=f"expected value >= {minimum}",
            )
        )
    if maximum is not None and value > maximum:
        return int(
            _invalid_env_setting(
                name=name,
                raw=raw,
                default=default,
                reason=f"expected value <= {maximum}",
            )
        )
    return value


def _env_float(
    name: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return float(
            _invalid_env_setting(
                name=name,
                raw=raw,
                default=default,
                reason="expected numeric seconds value",
            )
        )
    if minimum is not None and value < minimum:
        return float(
            _invalid_env_setting(
                name=name,
                raw=raw,
                default=default,
                reason=f"expected value >= {minimum}",
            )
        )
    if maximum is not None and value > maximum:
        return float(
            _invalid_env_setting(
                name=name,
                raw=raw,
                default=default,
                reason=f"expected value <= {maximum}",
            )
        )
    return value


def _env_decimal(
    name: str,
    default: str,
    *,
    minimum: Decimal | None = None,
    maximum: Decimal | None = None,
) -> Decimal:
    raw = os.getenv(name)
    if raw is None:
        return Decimal(default)
    try:
        value = Decimal(raw)
    except Exception:
        return Decimal(
            str(
                _invalid_env_setting(
                    name=name,
                    raw=raw,
                    default=default,
                    reason="expected decimal value",
                )
            )
        )
    if minimum is not None and value < minimum:
        return Decimal(
            str(
                _invalid_env_setting(
                    name=name,
                    raw=raw,
                    default=default,
                    reason=f"expected value >= {minimum}",
                )
            )
        )
    if maximum is not None and value > maximum:
        return Decimal(
            str(
                _invalid_env_setting(
                    name=name,
                    raw=raw,
                    default=default,
                    reason=f"expected value <= {maximum}",
                )
            )
        )
    return value


def _env_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    return default if raw is None else raw


def _strict_config_validation_enabled() -> bool:
    raw = os.getenv(STRICT_CONFIG_VALIDATION_ENV)
    if raw is not None:
        return raw.strip().lower() in TRUTHY_ENV_VALUES
    environment = os.getenv("ENVIRONMENT", "local").strip().lower()
    return environment not in LOCAL_CONFIG_ENVIRONMENTS


def _invalid_env_setting(
    *,
    name: str,
    raw: object,
    default: object,
    reason: str,
) -> object:
    if _strict_config_validation_enabled():
        raise IngestionConfigurationError(
            f"Invalid ingestion service configuration for {name}: {reason}"
        )
    logger.warning(
        "Invalid ingestion service setting; falling back to default.",
        extra={"setting": name, "raw_value": str(raw), "default": str(default), "reason": reason},
    )
    return default


def _env_choice(name: str, default: str, allowed_values: set[str]) -> str:
    raw = _env_str(name, default)
    if raw in allowed_values:
        return raw
    return str(
        _invalid_env_setting(
            name=name,
            raw=raw,
            default=default,
            reason=f"expected one of {sorted(allowed_values)}",
        )
    )


@dataclass(frozen=True, slots=True)
class IngestionOpsAuthSettings:
    token_required: bool
    token_value: str
    auth_mode: Literal["token_or_jwt", "jwt_only", "token_only"]
    jwt_hs256_secret: str
    jwt_key_id: str
    jwt_previous_keys: dict[str, str]
    jwt_issuer: str
    jwt_audience: str
    jwt_required_scope: str
    jwt_clock_skew_seconds: int
    static_token_non_local_approved: bool


@dataclass(frozen=True, slots=True)
class IngestionRateLimitSettings:
    enabled: bool
    window_seconds: int
    max_requests: int
    max_records: int
    enforcement_scope: IngestionRateLimitEnforcementScope
    gateway_policy_id: str


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
class IngestionAdapterModeSettings:
    portfolio_bundle_enabled: bool
    upload_apis_enabled: bool
    upload_max_bytes: int


@dataclass(frozen=True, slots=True)
class IngestionServiceSettings:
    adapter_mode: IngestionAdapterModeSettings
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
        _invalid_env_setting(
            name="LOTUS_CORE_CALCULATOR_PEAK_LAG_AGE_SECONDS_JSON",
            raw=raw,
            default=defaults,
            reason="expected JSON object",
        )
        return dict(defaults)
    if not isinstance(parsed, dict):
        _invalid_env_setting(
            name="LOTUS_CORE_CALCULATOR_PEAK_LAG_AGE_SECONDS_JSON",
            raw=raw,
            default=defaults,
            reason="expected JSON object",
        )
        return dict(defaults)
    return {key: _env_int_from_mapping(parsed, key, default) for key, default in defaults.items()}


def _load_ops_jwt_previous_keys() -> dict[str, str]:
    raw = os.getenv("LOTUS_CORE_INGEST_OPS_JWT_PREVIOUS_KEYS_JSON")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        _invalid_env_setting(
            name="LOTUS_CORE_INGEST_OPS_JWT_PREVIOUS_KEYS_JSON",
            raw=raw,
            default={},
            reason="expected JSON object mapping key ids to secrets",
        )
        return {}
    if not isinstance(parsed, dict):
        _invalid_env_setting(
            name="LOTUS_CORE_INGEST_OPS_JWT_PREVIOUS_KEYS_JSON",
            raw=raw,
            default={},
            reason="expected JSON object mapping key ids to secrets",
        )
        return {}
    previous_keys: dict[str, str] = {}
    for key_id, secret in parsed.items():
        if not isinstance(key_id, str) or not key_id.strip():
            _invalid_env_setting(
                name="LOTUS_CORE_INGEST_OPS_JWT_PREVIOUS_KEYS_JSON",
                raw=raw,
                default={},
                reason="expected non-empty string key ids",
            )
            return {}
        if not isinstance(secret, str) or not secret.strip():
            _invalid_env_setting(
                name=f"LOTUS_CORE_INGEST_OPS_JWT_PREVIOUS_KEYS_JSON.{key_id}",
                raw=secret,
                default="",
                reason="expected non-empty secret value",
            )
            return {}
        previous_keys[key_id.strip()] = secret
    return previous_keys


def _validate_ops_auth_settings(settings: IngestionOpsAuthSettings) -> None:
    if not _strict_config_validation_enabled():
        return
    jwt_enabled = settings.auth_mode in {"token_or_jwt", "jwt_only"}
    static_token_enabled = settings.auth_mode in {"token_or_jwt", "token_only"}

    if jwt_enabled:
        missing_jwt_settings = [
            name
            for name, value in (
                ("LOTUS_CORE_INGEST_OPS_JWT_HS256_SECRET", settings.jwt_hs256_secret),
                ("LOTUS_CORE_INGEST_OPS_JWT_KEY_ID", settings.jwt_key_id),
                ("LOTUS_CORE_INGEST_OPS_JWT_ISSUER", settings.jwt_issuer),
                ("LOTUS_CORE_INGEST_OPS_JWT_AUDIENCE", settings.jwt_audience),
                ("LOTUS_CORE_INGEST_OPS_JWT_REQUIRED_SCOPE", settings.jwt_required_scope),
            )
            if not value.strip()
        ]
        if settings.jwt_key_id.strip() == "local-dev":
            missing_jwt_settings.append("LOTUS_CORE_INGEST_OPS_JWT_KEY_ID")
        if settings.jwt_key_id in settings.jwt_previous_keys:
            raise IngestionConfigurationError(
                "Invalid ingestion service configuration for "
                "LOTUS_CORE_INGEST_OPS_JWT_PREVIOUS_KEYS_JSON: active key id must not also be "
                "listed as a previous key."
            )
        if missing_jwt_settings:
            missing = ", ".join(sorted(set(missing_jwt_settings)))
            raise IngestionConfigurationError(
                "Invalid ingestion service configuration for ingestion ops JWT auth: "
                f"strict profiles require non-local values for {missing}."
            )

    if static_token_enabled and settings.token_required:
        if not settings.static_token_non_local_approved:
            raise IngestionConfigurationError(
                "Invalid ingestion service configuration for "
                "LOTUS_CORE_INGEST_OPS_STATIC_TOKEN_NON_LOCAL_APPROVED: strict profiles cannot "
                "enable static ingestion ops token fallback unless explicitly approved."
            )
        if not settings.token_value.strip() or settings.token_value == "lotus-core-ops-local":
            raise IngestionConfigurationError(
                "Invalid ingestion service configuration for LOTUS_CORE_INGEST_OPS_TOKEN: "
                "strict profiles require a non-default static ops token when static token auth is "
                "explicitly approved."
            )


def _env_int_from_mapping(values: dict[str, object], key: str, default: int) -> int:
    raw = values.get(key)
    try:
        value = int(raw) if raw is not None else default
    except (TypeError, ValueError):
        return int(
            _invalid_env_setting(
                name=f"LOTUS_CORE_CALCULATOR_PEAK_LAG_AGE_SECONDS_JSON.{key}",
                raw=raw,
                default=default,
                reason="expected integer seconds value",
            )
        )
    if value < 0:
        return int(
            _invalid_env_setting(
                name=f"LOTUS_CORE_CALCULATOR_PEAK_LAG_AGE_SECONDS_JSON.{key}",
                raw=raw,
                default=default,
                reason="expected value >= 0",
            )
        )
    return value


def load_ingestion_service_settings() -> IngestionServiceSettings:
    auth_mode = cast(
        Literal["token_or_jwt", "jwt_only", "token_only"],
        _env_choice(
            "LOTUS_CORE_INGEST_OPS_AUTH_MODE",
            "token_or_jwt",
            {"token_or_jwt", "jwt_only", "token_only"},
        ),
    )
    rate_limit_scope = cast(
        IngestionRateLimitEnforcementScope,
        _env_choice(
            "LOTUS_CORE_INGEST_RATE_LIMIT_ENFORCEMENT_SCOPE",
            "local_process",
            {
                "local_process",
                "upstream_gateway",
                "local_process_with_upstream_gateway",
            },
        ),
    )

    settings = IngestionServiceSettings(
        adapter_mode=IngestionAdapterModeSettings(
            portfolio_bundle_enabled=_env_bool("LOTUS_CORE_INGEST_PORTFOLIO_BUNDLE_ENABLED", True),
            upload_apis_enabled=_env_bool("LOTUS_CORE_INGEST_UPLOAD_APIS_ENABLED", True),
            upload_max_bytes=_env_int(
                "LOTUS_CORE_INGEST_UPLOAD_MAX_BYTES",
                5_242_880,
                minimum=1,
            ),
        ),
        ops_auth=IngestionOpsAuthSettings(
            token_required=_env_bool("LOTUS_CORE_INGEST_OPS_TOKEN_REQUIRED", True),
            token_value=_env_str("LOTUS_CORE_INGEST_OPS_TOKEN", "lotus-core-ops-local"),
            auth_mode=auth_mode,
            jwt_hs256_secret=_env_str("LOTUS_CORE_INGEST_OPS_JWT_HS256_SECRET", ""),
            jwt_key_id=_env_str("LOTUS_CORE_INGEST_OPS_JWT_KEY_ID", "local-dev"),
            jwt_previous_keys=_load_ops_jwt_previous_keys(),
            jwt_issuer=_env_str("LOTUS_CORE_INGEST_OPS_JWT_ISSUER", ""),
            jwt_audience=_env_str("LOTUS_CORE_INGEST_OPS_JWT_AUDIENCE", ""),
            jwt_required_scope=_env_str(
                "LOTUS_CORE_INGEST_OPS_JWT_REQUIRED_SCOPE",
                "lotus-core.ingestion.ops",
            ),
            jwt_clock_skew_seconds=_env_int(
                "LOTUS_CORE_INGEST_OPS_JWT_CLOCK_SKEW_SECONDS", 60, minimum=0
            ),
            static_token_non_local_approved=_env_bool(
                "LOTUS_CORE_INGEST_OPS_STATIC_TOKEN_NON_LOCAL_APPROVED", False
            ),
        ),
        rate_limit=IngestionRateLimitSettings(
            enabled=_env_bool("LOTUS_CORE_INGEST_RATE_LIMIT_ENABLED", True),
            window_seconds=_env_int("LOTUS_CORE_INGEST_RATE_LIMIT_WINDOW_SECONDS", 60, minimum=1),
            max_requests=_env_int("LOTUS_CORE_INGEST_RATE_LIMIT_MAX_REQUESTS", 120, minimum=1),
            max_records=_env_int("LOTUS_CORE_INGEST_RATE_LIMIT_MAX_RECORDS", 10000, minimum=1),
            enforcement_scope=rate_limit_scope,
            gateway_policy_id=_env_str("LOTUS_CORE_INGEST_RATE_LIMIT_GATEWAY_POLICY_ID", ""),
        ),
        runtime_policy=IngestionRuntimePolicySettings(
            replay_max_records_per_request=_env_int(
                "LOTUS_CORE_REPLAY_MAX_RECORDS_PER_REQUEST", 5000, minimum=1
            ),
            replay_max_backlog_jobs=_env_int("LOTUS_CORE_REPLAY_MAX_BACKLOG_JOBS", 5000, minimum=1),
            dlq_budget_events_per_window=_env_int(
                "LOTUS_CORE_DLQ_EVENTS_BUDGET_PER_WINDOW", 10, minimum=0
            ),
            default_lookback_minutes=_env_int("LOTUS_CORE_DEFAULT_LOOKBACK_MINUTES", 60, minimum=1),
            default_failure_rate_threshold=_env_decimal(
                "LOTUS_CORE_DEFAULT_FAILURE_RATE_THRESHOLD",
                "0.03",
                minimum=Decimal("0"),
            ),
            default_queue_latency_threshold_seconds=_env_float(
                "LOTUS_CORE_DEFAULT_QUEUE_LATENCY_THRESHOLD_SECONDS", 5.0, minimum=0.0
            ),
            default_backlog_age_threshold_seconds=_env_float(
                "LOTUS_CORE_DEFAULT_BACKLOG_AGE_THRESHOLD_SECONDS", 300.0, minimum=0.0
            ),
            reprocessing_worker_poll_interval_seconds=_env_int(
                "REPROCESSING_WORKER_POLL_INTERVAL_SECONDS", 10, minimum=1
            ),
            reprocessing_worker_batch_size=_env_int(
                "REPROCESSING_WORKER_BATCH_SIZE", 10, minimum=1
            ),
            valuation_scheduler_poll_interval_seconds=_env_int(
                "VALUATION_SCHEDULER_POLL_INTERVAL", 30, minimum=1
            ),
            valuation_scheduler_batch_size=_env_int(
                "VALUATION_SCHEDULER_BATCH_SIZE", 100, minimum=1
            ),
            valuation_scheduler_dispatch_rounds=_env_int(
                "VALUATION_SCHEDULER_DISPATCH_ROUNDS", 10, minimum=1
            ),
            capacity_assumed_replicas=_env_int(
                "LOTUS_CORE_CAPACITY_ASSUMED_REPLICAS", 1, minimum=1
            ),
            replay_isolation_mode=_env_str("LOTUS_CORE_REPLAY_ISOLATION_MODE", "shared_workers"),
            partition_growth_strategy=_env_str(
                "LOTUS_CORE_PARTITION_GROWTH_STRATEGY", "scale_out_only"
            ),
            calculator_peak_lag_age_seconds=_load_calculator_peak_lag_age_seconds(),
            operating_band=IngestionOperatingBandSettings(
                yellow_backlog_age_seconds=_env_float(
                    "LOTUS_CORE_OPERATING_BAND_YELLOW_BACKLOG_AGE_SECONDS", 15.0, minimum=0.0
                ),
                orange_backlog_age_seconds=_env_float(
                    "LOTUS_CORE_OPERATING_BAND_ORANGE_BACKLOG_AGE_SECONDS", 60.0, minimum=0.0
                ),
                red_backlog_age_seconds=_env_float(
                    "LOTUS_CORE_OPERATING_BAND_RED_BACKLOG_AGE_SECONDS", 180.0, minimum=0.0
                ),
                yellow_dlq_pressure_ratio=_env_decimal(
                    "LOTUS_CORE_OPERATING_BAND_YELLOW_DLQ_PRESSURE_RATIO",
                    "0.25",
                    minimum=Decimal("0"),
                ),
                orange_dlq_pressure_ratio=_env_decimal(
                    "LOTUS_CORE_OPERATING_BAND_ORANGE_DLQ_PRESSURE_RATIO",
                    "0.50",
                    minimum=Decimal("0"),
                ),
                red_dlq_pressure_ratio=_env_decimal(
                    "LOTUS_CORE_OPERATING_BAND_RED_DLQ_PRESSURE_RATIO",
                    "1.0",
                    minimum=Decimal("0"),
                ),
            ),
        ),
    )
    _validate_ops_auth_settings(settings.ops_auth)
    return settings


def get_ingestion_service_settings() -> IngestionServiceSettings:
    return load_ingestion_service_settings()
