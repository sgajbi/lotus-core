from __future__ import annotations

import pytest

from src.services.query_service.app.settings import (
    QueryServiceConfigurationError,
    env_bool,
    env_int,
    env_json_map,
    load_query_service_settings,
)


def test_query_service_settings_parse_enterprise_defaults(monkeypatch) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("LOTUS_CORE_STRICT_CONFIG_VALIDATION", raising=False)
    monkeypatch.delenv("LOTUS_CORE_PRODUCTION_SECURITY_PROFILE", raising=False)
    for name in (
        "ENTERPRISE_POLICY_VERSION",
        "ENTERPRISE_ENFORCE_AUTHZ",
        "ENTERPRISE_ENFORCE_READ_AUTHZ",
        "ENTERPRISE_AUDIT_READS",
        "ENTERPRISE_REQUIRE_CAPABILITY_RULES",
        "ENTERPRISE_ENFORCE_RUNTIME_CONFIG",
        "ENTERPRISE_PRIMARY_KEY_ID",
        "ENTERPRISE_SECRET_ROTATION_DAYS",
        "ENTERPRISE_MAX_WRITE_PAYLOAD_BYTES",
        "ENTERPRISE_FEATURE_FLAGS_JSON",
        "ENTERPRISE_CAPABILITY_RULES_JSON",
        "LOTUS_CORE_ANALYTICS_EXPORT_EXECUTION_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = load_query_service_settings()

    assert settings.analytics_export_execution_timeout_seconds == 300
    assert settings.enterprise_policy_version == "1.0.0"
    assert settings.enterprise_enforce_authz is False
    assert settings.enterprise_enforce_read_authz is False
    assert settings.enterprise_audit_reads is False
    assert settings.enterprise_require_capability_rules is False
    assert settings.enterprise_enforce_runtime_config is False
    assert settings.enterprise_primary_key_id == ""
    assert settings.enterprise_secret_rotation_days == 90
    assert settings.enterprise_max_write_payload_bytes == 1_048_576
    assert settings.enterprise_feature_flags == {}
    assert settings.enterprise_capability_rules == {}


def test_query_service_settings_enable_production_security_profile(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("LOTUS_CORE_PRODUCTION_SECURITY_PROFILE", raising=False)
    for name in (
        "ENTERPRISE_ENFORCE_AUTHZ",
        "ENTERPRISE_ENFORCE_READ_AUTHZ",
        "ENTERPRISE_AUDIT_READS",
        "ENTERPRISE_REQUIRE_CAPABILITY_RULES",
        "ENTERPRISE_ENFORCE_RUNTIME_CONFIG",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = load_query_service_settings()

    assert settings.enterprise_enforce_authz is True
    assert settings.enterprise_enforce_read_authz is True
    assert settings.enterprise_audit_reads is True
    assert settings.enterprise_require_capability_rules is True
    assert settings.enterprise_enforce_runtime_config is True


def test_query_service_settings_allow_explicit_production_security_opt_out(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LOTUS_CORE_PRODUCTION_SECURITY_PROFILE", "false")

    settings = load_query_service_settings()

    assert settings.enterprise_enforce_authz is False
    assert settings.enterprise_enforce_read_authz is False
    assert settings.enterprise_audit_reads is False
    assert settings.enterprise_require_capability_rules is False
    assert settings.enterprise_enforce_runtime_config is False


def test_query_service_settings_parse_enterprise_governed_values(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("ENTERPRISE_POLICY_VERSION", "2.3.1")
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "true")
    monkeypatch.setenv("ENTERPRISE_ENFORCE_READ_AUTHZ", "true")
    monkeypatch.setenv("ENTERPRISE_AUDIT_READS", "yes")
    monkeypatch.setenv("ENTERPRISE_REQUIRE_CAPABILITY_RULES", "on")
    monkeypatch.setenv("ENTERPRISE_ENFORCE_RUNTIME_CONFIG", "yes")
    monkeypatch.setenv("ENTERPRISE_PRIMARY_KEY_ID", "kms-key-1")
    monkeypatch.setenv("ENTERPRISE_SECRET_ROTATION_DAYS", "45")
    monkeypatch.setenv("ENTERPRISE_MAX_WRITE_PAYLOAD_BYTES", "2048")
    monkeypatch.setenv("LOTUS_CORE_ANALYTICS_EXPORT_EXECUTION_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv(
        "ENTERPRISE_FEATURE_FLAGS_JSON",
        '{"query.advanced":{"tenant-a":{"ops":true,"*":false}}}',
    )
    monkeypatch.setenv(
        "ENTERPRISE_CAPABILITY_RULES_JSON",
        '{"GET /portfolios/**":"portfolios.read"}',
    )

    settings = load_query_service_settings()

    assert settings.enterprise_policy_version == "2.3.1"
    assert settings.enterprise_enforce_authz is True
    assert settings.enterprise_enforce_read_authz is True
    assert settings.enterprise_audit_reads is True
    assert settings.enterprise_require_capability_rules is True
    assert settings.enterprise_enforce_runtime_config is True
    assert settings.enterprise_primary_key_id == "kms-key-1"
    assert settings.enterprise_secret_rotation_days == 45
    assert settings.enterprise_max_write_payload_bytes == 2048
    assert settings.analytics_export_execution_timeout_seconds == 45
    assert settings.enterprise_feature_flags == {
        "query.advanced": {"tenant-a": {"ops": True, "*": False}}
    }
    assert settings.enterprise_capability_rules == {"GET /portfolios/**": "portfolios.read"}


def test_query_service_settings_helpers_fail_closed_for_invalid_values(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("QUERY_BOOL", "maybe")
    monkeypatch.setenv("QUERY_INT", "not-an-int")
    monkeypatch.setenv("QUERY_JSON", "[]")

    assert env_bool("QUERY_BOOL", False) is False
    assert env_int("QUERY_INT", 11) == 11
    assert env_json_map("QUERY_JSON") == {}


def test_query_service_settings_strict_rejects_invalid_integer(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LOTUS_CORE_ANALYTICS_EXPORT_EXECUTION_TIMEOUT_SECONDS", "not-an-int")

    with pytest.raises(
        QueryServiceConfigurationError,
        match="LOTUS_CORE_ANALYTICS_EXPORT_EXECUTION_TIMEOUT_SECONDS",
    ):
        load_query_service_settings()


def test_query_service_settings_strict_rejects_out_of_range_payload_size(monkeypatch) -> None:
    monkeypatch.setenv("LOTUS_CORE_STRICT_CONFIG_VALIDATION", "true")
    monkeypatch.setenv("ENTERPRISE_MAX_WRITE_PAYLOAD_BYTES", "0")

    with pytest.raises(QueryServiceConfigurationError, match="ENTERPRISE_MAX_WRITE_PAYLOAD_BYTES"):
        load_query_service_settings()


def test_query_service_settings_strict_rejects_invalid_json_map(monkeypatch) -> None:
    monkeypatch.setenv("LOTUS_CORE_STRICT_CONFIG_VALIDATION", "true")
    monkeypatch.setenv("ENTERPRISE_FEATURE_FLAGS_JSON", "[]")

    with pytest.raises(QueryServiceConfigurationError, match="ENTERPRISE_FEATURE_FLAGS_JSON"):
        load_query_service_settings()
