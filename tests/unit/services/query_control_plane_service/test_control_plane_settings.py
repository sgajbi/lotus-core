from __future__ import annotations

import pytest

from src.services.query_control_plane_service.app.settings import (
    QueryControlPlaneConfigurationError,
    env_bool,
    env_int,
    env_json_map,
    load_query_control_plane_settings,
)


def _set_non_default_page_token_material(monkeypatch) -> None:
    monkeypatch.setenv("LOTUS_CORE_PAGE_TOKEN_SECRET", "qcp-page-token-secret")
    monkeypatch.setenv("LOTUS_CORE_PAGE_TOKEN_KEY_ID", "qcp-page-token-key-2026-07")


def test_control_plane_settings_parse_defaults(monkeypatch) -> None:
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
        "ENTERPRISE_AUTH_CONTEXT_HMAC_SECRET",
        "ENTERPRISE_AUTH_CONTEXT_MAX_AGE_SECONDS",
        "ENTERPRISE_FEATURE_FLAGS_JSON",
        "ENTERPRISE_CAPABILITY_RULES_JSON",
        "LOTUS_CORE_ANALYTICS_EXPORT_EXECUTION_TIMEOUT_SECONDS",
        "LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON",
        "LOTUS_CORE_POLICY_VERSION",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = load_query_control_plane_settings()

    assert settings.enterprise_policy_version == "1.0.0"
    assert settings.enterprise_enforce_authz is False
    assert settings.enterprise_enforce_read_authz is False
    assert settings.enterprise_audit_reads is False
    assert settings.enterprise_require_capability_rules is False
    assert settings.enterprise_enforce_runtime_config is False
    assert settings.enterprise_primary_key_id == ""
    assert settings.enterprise_secret_rotation_days == 90
    assert settings.enterprise_max_write_payload_bytes == 1_048_576
    assert settings.enterprise_auth_context_hmac_secret == ""
    assert settings.enterprise_auth_context_max_age_seconds == 300
    assert settings.enterprise_feature_flags == {}
    assert settings.enterprise_capability_rules == {}
    assert settings.analytics_export_execution_timeout_seconds == 300
    assert settings.integration_snapshot_policy_json == ""
    assert settings.lotus_core_policy_version == "tenant-default-v1"
    assert settings.page_token_key_id == "local-dev"
    assert settings.page_token_previous_keys == {}
    assert settings.page_token_ttl_seconds == 900


def test_control_plane_settings_enable_production_security_profile(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "uat")
    monkeypatch.delenv("LOTUS_CORE_PRODUCTION_SECURITY_PROFILE", raising=False)
    _set_non_default_page_token_material(monkeypatch)
    for name in (
        "ENTERPRISE_ENFORCE_AUTHZ",
        "ENTERPRISE_ENFORCE_READ_AUTHZ",
        "ENTERPRISE_AUDIT_READS",
        "ENTERPRISE_REQUIRE_CAPABILITY_RULES",
        "ENTERPRISE_ENFORCE_RUNTIME_CONFIG",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = load_query_control_plane_settings()

    assert settings.enterprise_enforce_authz is True
    assert settings.enterprise_enforce_read_authz is True
    assert settings.enterprise_audit_reads is True
    assert settings.enterprise_require_capability_rules is True
    assert settings.enterprise_enforce_runtime_config is True


def test_control_plane_settings_allow_explicit_production_security_opt_out(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LOTUS_CORE_PRODUCTION_SECURITY_PROFILE", "false")
    _set_non_default_page_token_material(monkeypatch)

    settings = load_query_control_plane_settings()

    assert settings.enterprise_enforce_authz is False
    assert settings.enterprise_enforce_read_authz is False
    assert settings.enterprise_audit_reads is False
    assert settings.enterprise_require_capability_rules is False
    assert settings.enterprise_enforce_runtime_config is False


def test_control_plane_settings_parse_governed_values(monkeypatch) -> None:
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
    monkeypatch.setenv("ENTERPRISE_AUTH_CONTEXT_HMAC_SECRET", "auth-context-secret")
    monkeypatch.setenv("ENTERPRISE_AUTH_CONTEXT_MAX_AGE_SECONDS", "120")
    monkeypatch.setenv("LOTUS_CORE_ANALYTICS_EXPORT_EXECUTION_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("LOTUS_CORE_PAGE_TOKEN_SECRET", "qcp-page-token-secret")
    monkeypatch.setenv("LOTUS_CORE_PAGE_TOKEN_KEY_ID", "qcp-page-token-key-2026-07")
    monkeypatch.setenv(
        "LOTUS_CORE_PAGE_TOKEN_PREVIOUS_KEYS_JSON",
        '{"qcp-page-token-key-2026-06":"previous-secret"}',
    )
    monkeypatch.setenv("LOTUS_CORE_PAGE_TOKEN_TTL_SECONDS", "1200")
    monkeypatch.setenv(
        "ENTERPRISE_FEATURE_FLAGS_JSON",
        '{"risk_write":{"tenant-a":{"ops":true,"*":false}}}',
    )
    monkeypatch.setenv(
        "ENTERPRISE_CAPABILITY_RULES_JSON",
        '{"POST /integration":"risk.write"}',
    )

    settings = load_query_control_plane_settings()

    assert settings.enterprise_policy_version == "2.3.1"
    assert settings.enterprise_enforce_authz is True
    assert settings.enterprise_enforce_read_authz is True
    assert settings.enterprise_audit_reads is True
    assert settings.enterprise_require_capability_rules is True
    assert settings.enterprise_enforce_runtime_config is True
    assert settings.enterprise_primary_key_id == "kms-key-1"
    assert settings.enterprise_secret_rotation_days == 45
    assert settings.enterprise_max_write_payload_bytes == 2048
    assert settings.enterprise_auth_context_hmac_secret == "auth-context-secret"
    assert settings.enterprise_auth_context_max_age_seconds == 120
    assert settings.enterprise_feature_flags == {
        "risk_write": {"tenant-a": {"ops": True, "*": False}}
    }
    assert settings.enterprise_capability_rules == {"POST /integration": "risk.write"}
    assert settings.analytics_export_execution_timeout_seconds == 45
    assert settings.page_token_secret == "qcp-page-token-secret"
    assert settings.page_token_key_id == "qcp-page-token-key-2026-07"
    assert settings.page_token_previous_keys == {"qcp-page-token-key-2026-06": "previous-secret"}
    assert settings.page_token_ttl_seconds == 1200


def test_control_plane_settings_non_local_rejects_default_page_token_secret(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("LOTUS_CORE_PAGE_TOKEN_SECRET", raising=False)
    monkeypatch.setenv("LOTUS_CORE_PAGE_TOKEN_KEY_ID", "qcp-page-token-key-2026-07")

    with pytest.raises(QueryControlPlaneConfigurationError, match="LOTUS_CORE_PAGE_TOKEN_SECRET"):
        load_query_control_plane_settings()


def test_control_plane_settings_non_local_rejects_default_page_token_key_id(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LOTUS_CORE_PAGE_TOKEN_SECRET", "qcp-page-token-secret")
    monkeypatch.delenv("LOTUS_CORE_PAGE_TOKEN_KEY_ID", raising=False)

    with pytest.raises(QueryControlPlaneConfigurationError, match="LOTUS_CORE_PAGE_TOKEN_KEY_ID"):
        load_query_control_plane_settings()


def test_control_plane_settings_helpers_fail_closed_for_invalid_values(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("CONTROL_BOOL", "maybe")
    monkeypatch.setenv("CONTROL_INT", "not-an-int")
    monkeypatch.setenv("CONTROL_JSON", "[]")

    assert env_bool("CONTROL_BOOL", False) is False
    assert env_int("CONTROL_INT", 11) == 11
    assert env_json_map("CONTROL_JSON") == {}


def test_control_plane_settings_strict_rejects_invalid_boolean(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    _set_non_default_page_token_material(monkeypatch)
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "maybe")

    with pytest.raises(QueryControlPlaneConfigurationError, match="ENTERPRISE_ENFORCE_AUTHZ"):
        load_query_control_plane_settings()


def test_control_plane_settings_strict_rejects_out_of_range_rotation_days(monkeypatch) -> None:
    monkeypatch.setenv("LOTUS_CORE_STRICT_CONFIG_VALIDATION", "true")
    _set_non_default_page_token_material(monkeypatch)
    monkeypatch.setenv("ENTERPRISE_SECRET_ROTATION_DAYS", "0")

    with pytest.raises(
        QueryControlPlaneConfigurationError, match="ENTERPRISE_SECRET_ROTATION_DAYS"
    ):
        load_query_control_plane_settings()


def test_control_plane_settings_strict_rejects_invalid_analytics_timeout(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    _set_non_default_page_token_material(monkeypatch)
    monkeypatch.setenv("LOTUS_CORE_ANALYTICS_EXPORT_EXECUTION_TIMEOUT_SECONDS", "not-an-int")

    with pytest.raises(
        QueryControlPlaneConfigurationError,
        match="LOTUS_CORE_ANALYTICS_EXPORT_EXECUTION_TIMEOUT_SECONDS",
    ):
        load_query_control_plane_settings()


def test_control_plane_settings_strict_rejects_invalid_json_map(monkeypatch) -> None:
    monkeypatch.setenv("LOTUS_CORE_STRICT_CONFIG_VALIDATION", "true")
    _set_non_default_page_token_material(monkeypatch)
    monkeypatch.setenv("ENTERPRISE_CAPABILITY_RULES_JSON", "not-json")

    with pytest.raises(
        QueryControlPlaneConfigurationError, match="ENTERPRISE_CAPABILITY_RULES_JSON"
    ):
        load_query_control_plane_settings()
