import logging
from decimal import Decimal

import pytest

from src.services.ingestion_service.app.settings import (
    IngestionConfigurationError,
    load_ingestion_service_settings,
)


def test_load_ingestion_service_settings_defaults(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("LOTUS_CORE_STRICT_CONFIG_VALIDATION", raising=False)
    monkeypatch.delenv("LOTUS_CORE_INGEST_OPS_JWT_HS256_SECRET", raising=False)
    monkeypatch.delenv("LOTUS_CORE_INGEST_OPS_JWT_KEY_ID", raising=False)
    monkeypatch.delenv("LOTUS_CORE_INGEST_OPS_JWT_PREVIOUS_KEYS_JSON", raising=False)
    monkeypatch.delenv("LOTUS_CORE_INGEST_OPS_JWT_ISSUER", raising=False)
    monkeypatch.delenv("LOTUS_CORE_INGEST_OPS_JWT_AUDIENCE", raising=False)
    monkeypatch.delenv("LOTUS_CORE_INGEST_OPS_JWT_REQUIRED_SCOPE", raising=False)
    monkeypatch.delenv("LOTUS_CORE_INGEST_OPS_STATIC_TOKEN_NON_LOCAL_APPROVED", raising=False)
    monkeypatch.delenv("LOTUS_CORE_REPLAY_MAX_RECORDS_PER_REQUEST", raising=False)
    monkeypatch.delenv("LOTUS_CORE_DEFAULT_FAILURE_RATE_THRESHOLD", raising=False)
    monkeypatch.delenv("LOTUS_CORE_CALCULATOR_PEAK_LAG_AGE_SECONDS_JSON", raising=False)

    settings = load_ingestion_service_settings()

    assert settings.runtime_policy.replay_max_records_per_request == 5000
    assert settings.runtime_policy.default_failure_rate_threshold == Decimal("0.03")
    assert settings.runtime_policy.calculator_peak_lag_age_seconds["position"] == 30
    assert settings.ops_auth.auth_mode == "token_or_jwt"
    assert settings.ops_auth.jwt_key_id == "local-dev"
    assert settings.ops_auth.jwt_previous_keys == {}
    assert settings.ops_auth.jwt_required_scope == "lotus-core.ingestion.ops"
    assert settings.ops_auth.static_token_non_local_approved is False
    assert settings.rate_limit.enforcement_scope == "local_process"
    assert settings.rate_limit.gateway_policy_id == ""
    assert settings.adapter_mode.upload_max_bytes == 5_242_880


def test_load_ingestion_service_settings_invalid_json_falls_back(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("LOTUS_CORE_CALCULATOR_PEAK_LAG_AGE_SECONDS_JSON", "not-json")

    settings = load_ingestion_service_settings()

    assert settings.runtime_policy.calculator_peak_lag_age_seconds == {
        "position": 30,
        "cost": 45,
        "valuation": 60,
        "cashflow": 45,
        "timeseries": 120,
    }


def test_load_ingestion_service_settings_coerces_env_values(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("LOTUS_CORE_INGEST_OPS_AUTH_MODE", "jwt_only")
    monkeypatch.setenv("LOTUS_CORE_INGEST_OPS_JWT_KEY_ID", "ops-key-current")
    monkeypatch.setenv(
        "LOTUS_CORE_INGEST_OPS_JWT_PREVIOUS_KEYS_JSON",
        '{"ops-key-previous":"previous-secret"}',
    )
    monkeypatch.setenv(
        "LOTUS_CORE_INGEST_RATE_LIMIT_ENFORCEMENT_SCOPE",
        "local_process_with_upstream_gateway",
    )
    monkeypatch.setenv("LOTUS_CORE_INGEST_RATE_LIMIT_GATEWAY_POLICY_ID", "kong-ingest-write-v1")
    monkeypatch.setenv("LOTUS_CORE_DEFAULT_FAILURE_RATE_THRESHOLD", "0.125")
    monkeypatch.setenv("LOTUS_CORE_OPERATING_BAND_RED_DLQ_PRESSURE_RATIO", "2.5")
    monkeypatch.setenv(
        "LOTUS_CORE_CALCULATOR_PEAK_LAG_AGE_SECONDS_JSON",
        '{"position": 99, "timeseries": 300}',
    )

    settings = load_ingestion_service_settings()

    assert settings.ops_auth.auth_mode == "jwt_only"
    assert settings.ops_auth.jwt_key_id == "ops-key-current"
    assert settings.ops_auth.jwt_previous_keys == {"ops-key-previous": "previous-secret"}
    assert settings.rate_limit.enforcement_scope == "local_process_with_upstream_gateway"
    assert settings.rate_limit.gateway_policy_id == "kong-ingest-write-v1"
    assert settings.runtime_policy.default_failure_rate_threshold == Decimal("0.125")
    assert settings.runtime_policy.operating_band.red_dlq_pressure_ratio == Decimal("2.5")
    assert settings.runtime_policy.calculator_peak_lag_age_seconds["position"] == 99
    assert settings.runtime_policy.calculator_peak_lag_age_seconds["timeseries"] == 300


def test_load_ingestion_service_settings_adapter_mode_flags(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("LOTUS_CORE_INGEST_PORTFOLIO_BUNDLE_ENABLED", "false")
    monkeypatch.setenv("LOTUS_CORE_INGEST_UPLOAD_APIS_ENABLED", "0")
    monkeypatch.setenv("LOTUS_CORE_INGEST_UPLOAD_MAX_BYTES", "1024")

    settings = load_ingestion_service_settings()

    assert settings.adapter_mode.portfolio_bundle_enabled is False
    assert settings.adapter_mode.upload_apis_enabled is False
    assert settings.adapter_mode.upload_max_bytes == 1024


def test_load_ingestion_service_settings_invalid_rate_limit_scope_falls_back(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("LOTUS_CORE_INGEST_RATE_LIMIT_ENFORCEMENT_SCOPE", "global_magic")

    settings = load_ingestion_service_settings()

    assert settings.rate_limit.enforcement_scope == "local_process"


def test_load_ingestion_service_settings_strict_rejects_invalid_float(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LOTUS_CORE_DEFAULT_QUEUE_LATENCY_THRESHOLD_SECONDS", "not-a-number")

    with pytest.raises(
        IngestionConfigurationError,
        match="LOTUS_CORE_DEFAULT_QUEUE_LATENCY_THRESHOLD_SECONDS",
    ):
        load_ingestion_service_settings()


def test_load_ingestion_service_settings_strict_rejects_out_of_range_int(monkeypatch):
    monkeypatch.setenv("LOTUS_CORE_STRICT_CONFIG_VALIDATION", "true")
    monkeypatch.setenv("REPROCESSING_WORKER_BATCH_SIZE", "0")

    with pytest.raises(IngestionConfigurationError, match="REPROCESSING_WORKER_BATCH_SIZE"):
        load_ingestion_service_settings()


def test_load_ingestion_service_settings_strict_rejects_invalid_json(monkeypatch):
    monkeypatch.setenv("LOTUS_CORE_STRICT_CONFIG_VALIDATION", "true")
    monkeypatch.setenv("LOTUS_CORE_CALCULATOR_PEAK_LAG_AGE_SECONDS_JSON", "not-json")

    with pytest.raises(
        IngestionConfigurationError,
        match="LOTUS_CORE_CALCULATOR_PEAK_LAG_AGE_SECONDS_JSON",
    ):
        load_ingestion_service_settings()


def test_load_ingestion_service_settings_local_fallback_logs_warning(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="src.services.ingestion_service.app.settings")
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("LOTUS_CORE_DEFAULT_BACKLOG_AGE_THRESHOLD_SECONDS", "not-a-number")

    settings = load_ingestion_service_settings()

    assert settings.runtime_policy.default_backlog_age_threshold_seconds == 300.0
    assert "falling back to default" in caplog.text


def test_load_ingestion_service_settings_strict_rejects_missing_jwt_policy(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LOTUS_CORE_INGEST_OPS_AUTH_MODE", "jwt_only")

    with pytest.raises(IngestionConfigurationError, match="ingestion ops JWT auth"):
        load_ingestion_service_settings()


def test_load_ingestion_service_settings_strict_rejects_static_token_fallback(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LOTUS_CORE_INGEST_OPS_AUTH_MODE", "token_only")
    monkeypatch.setenv("LOTUS_CORE_INGEST_OPS_TOKEN", "prod-static-token")

    with pytest.raises(
        IngestionConfigurationError,
        match="LOTUS_CORE_INGEST_OPS_STATIC_TOKEN_NON_LOCAL_APPROVED",
    ):
        load_ingestion_service_settings()


def test_load_ingestion_service_settings_strict_accepts_approved_static_token(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LOTUS_CORE_INGEST_OPS_AUTH_MODE", "token_only")
    monkeypatch.setenv("LOTUS_CORE_INGEST_OPS_TOKEN", "prod-static-token")
    monkeypatch.setenv("LOTUS_CORE_INGEST_OPS_STATIC_TOKEN_NON_LOCAL_APPROVED", "true")

    settings = load_ingestion_service_settings()

    assert settings.ops_auth.auth_mode == "token_only"
    assert settings.ops_auth.static_token_non_local_approved is True


def test_load_ingestion_service_settings_strict_accepts_complete_jwt_policy(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LOTUS_CORE_INGEST_OPS_AUTH_MODE", "jwt_only")
    monkeypatch.setenv("LOTUS_CORE_INGEST_OPS_JWT_HS256_SECRET", "prod-hs256-secret")
    monkeypatch.setenv("LOTUS_CORE_INGEST_OPS_JWT_KEY_ID", "prod-key-current")
    monkeypatch.setenv("LOTUS_CORE_INGEST_OPS_JWT_ISSUER", "lotus-core-ingest-ops")
    monkeypatch.setenv("LOTUS_CORE_INGEST_OPS_JWT_AUDIENCE", "lotus-core-ingestion-ops")
    monkeypatch.setenv("LOTUS_CORE_INGEST_OPS_JWT_REQUIRED_SCOPE", "lotus-core.ingestion.ops")
    monkeypatch.setenv(
        "LOTUS_CORE_INGEST_OPS_JWT_PREVIOUS_KEYS_JSON",
        '{"prod-key-previous":"previous-secret"}',
    )

    settings = load_ingestion_service_settings()

    assert settings.ops_auth.jwt_key_id == "prod-key-current"
    assert settings.ops_auth.jwt_previous_keys == {"prod-key-previous": "previous-secret"}
