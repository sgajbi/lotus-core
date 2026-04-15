from __future__ import annotations

from src.services.query_service.app.settings import (
    env_bool,
    env_int,
    env_json_map,
    load_query_service_settings,
)


def test_query_service_settings_parse_enterprise_defaults(monkeypatch) -> None:
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
    ):
        monkeypatch.delenv(name, raising=False)

    settings = load_query_service_settings()

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


def test_query_service_settings_parse_enterprise_governed_values(monkeypatch) -> None:
    monkeypatch.setenv("ENTERPRISE_POLICY_VERSION", "2.3.1")
    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "true")
    monkeypatch.setenv("ENTERPRISE_ENFORCE_READ_AUTHZ", "true")
    monkeypatch.setenv("ENTERPRISE_AUDIT_READS", "yes")
    monkeypatch.setenv("ENTERPRISE_REQUIRE_CAPABILITY_RULES", "on")
    monkeypatch.setenv("ENTERPRISE_ENFORCE_RUNTIME_CONFIG", "yes")
    monkeypatch.setenv("ENTERPRISE_PRIMARY_KEY_ID", "kms-key-1")
    monkeypatch.setenv("ENTERPRISE_SECRET_ROTATION_DAYS", "45")
    monkeypatch.setenv("ENTERPRISE_MAX_WRITE_PAYLOAD_BYTES", "2048")
    monkeypatch.setenv(
        "ENTERPRISE_FEATURE_FLAGS_JSON",
        '{"query.advanced":{"tenant-a":{"ops":true,"*":false}}}',
    )
    monkeypatch.setenv(
        "ENTERPRISE_CAPABILITY_RULES_JSON",
        '{"GET /portfolios":"portfolios.read"}',
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
    assert settings.enterprise_feature_flags == {
        "query.advanced": {"tenant-a": {"ops": True, "*": False}}
    }
    assert settings.enterprise_capability_rules == {"GET /portfolios": "portfolios.read"}


def test_query_service_settings_helpers_fail_closed_for_invalid_values(monkeypatch) -> None:
    monkeypatch.setenv("QUERY_BOOL", "maybe")
    monkeypatch.setenv("QUERY_INT", "not-an-int")
    monkeypatch.setenv("QUERY_JSON", "[]")

    assert env_bool("QUERY_BOOL", False) is False
    assert env_int("QUERY_INT", 11) == 11
    assert env_json_map("QUERY_JSON") == {}
