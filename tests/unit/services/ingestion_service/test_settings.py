from decimal import Decimal

from src.services.ingestion_service.app.settings import load_ingestion_service_settings


def test_load_ingestion_service_settings_defaults(monkeypatch):
    monkeypatch.delenv("LOTUS_CORE_REPLAY_MAX_RECORDS_PER_REQUEST", raising=False)
    monkeypatch.delenv("LOTUS_CORE_DEFAULT_FAILURE_RATE_THRESHOLD", raising=False)
    monkeypatch.delenv("LOTUS_CORE_CALCULATOR_PEAK_LAG_AGE_SECONDS_JSON", raising=False)

    settings = load_ingestion_service_settings()

    assert settings.runtime_policy.replay_max_records_per_request == 5000
    assert settings.runtime_policy.default_failure_rate_threshold == Decimal("0.03")
    assert settings.runtime_policy.calculator_peak_lag_age_seconds["position"] == 30
    assert settings.ops_auth.auth_mode == "token_or_jwt"


def test_load_ingestion_service_settings_invalid_json_falls_back(monkeypatch):
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
    monkeypatch.setenv("LOTUS_CORE_INGEST_OPS_AUTH_MODE", "jwt_only")
    monkeypatch.setenv("LOTUS_CORE_DEFAULT_FAILURE_RATE_THRESHOLD", "0.125")
    monkeypatch.setenv("LOTUS_CORE_OPERATING_BAND_RED_DLQ_PRESSURE_RATIO", "2.5")
    monkeypatch.setenv(
        "LOTUS_CORE_CALCULATOR_PEAK_LAG_AGE_SECONDS_JSON",
        '{"position": 99, "timeseries": 300}',
    )

    settings = load_ingestion_service_settings()

    assert settings.ops_auth.auth_mode == "jwt_only"
    assert settings.runtime_policy.default_failure_rate_threshold == Decimal("0.125")
    assert settings.runtime_policy.operating_band.red_dlq_pressure_ratio == Decimal("2.5")
    assert settings.runtime_policy.calculator_peak_lag_age_seconds["position"] == 99
    assert settings.runtime_policy.calculator_peak_lag_age_seconds["timeseries"] == 300
