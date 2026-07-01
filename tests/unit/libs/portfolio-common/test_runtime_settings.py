from __future__ import annotations

import logging

import pytest
from portfolio_common.runtime_settings import (
    RuntimeConfigurationError,
    env_bool,
    env_int,
    env_json_map,
    production_security_profile_enabled,
    strict_config_validation_enabled,
)


def test_runtime_settings_default_to_local_fallback(monkeypatch, caplog) -> None:
    caplog.set_level(logging.WARNING, logger="portfolio_common.runtime_settings")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("LOTUS_CORE_STRICT_CONFIG_VALIDATION", raising=False)
    monkeypatch.setenv("LOTUS_TEST_BOOL", "maybe")
    monkeypatch.setenv("LOTUS_TEST_INT", "not-an-int")
    monkeypatch.setenv("LOTUS_TEST_JSON", "[]")

    assert strict_config_validation_enabled() is False
    assert env_bool("LOTUS_TEST_BOOL", False, service_name="unit service") is False
    assert env_int("LOTUS_TEST_INT", 11, service_name="unit service") == 11
    assert env_json_map("LOTUS_TEST_JSON", service_name="unit service") == {}
    assert "falling back to default" in caplog.text


def test_runtime_settings_strict_profile_rejects_invalid_boolean(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LOTUS_TEST_BOOL", "maybe")

    with pytest.raises(RuntimeConfigurationError, match="LOTUS_TEST_BOOL"):
        env_bool("LOTUS_TEST_BOOL", False, service_name="unit service")


def test_runtime_settings_explicit_strict_flag_rejects_out_of_range_int(monkeypatch) -> None:
    monkeypatch.setenv("LOTUS_CORE_STRICT_CONFIG_VALIDATION", "true")
    monkeypatch.setenv("LOTUS_TEST_INT", "0")

    with pytest.raises(RuntimeConfigurationError, match="expected value >= 1"):
        env_int("LOTUS_TEST_INT", 10, service_name="unit service", minimum=1)


def test_runtime_settings_local_minimum_fallback_can_preserve_clamp_behavior(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("LOTUS_TEST_INT", "0")

    assert (
        env_int(
            "LOTUS_TEST_INT",
            10,
            service_name="unit service",
            minimum=1,
            minimum_fallback=1,
        )
        == 1
    )


def test_runtime_settings_strict_profile_rejects_invalid_json(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("LOTUS_TEST_JSON", "not-json")

    with pytest.raises(RuntimeConfigurationError, match="LOTUS_TEST_JSON"):
        env_json_map("LOTUS_TEST_JSON", service_name="unit service")


def test_production_security_profile_follows_production_like_environments(monkeypatch) -> None:
    monkeypatch.delenv("LOTUS_CORE_PRODUCTION_SECURITY_PROFILE", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "staging")

    assert production_security_profile_enabled(service_name="unit service") is True


def test_production_security_profile_keeps_local_default_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("LOTUS_CORE_PRODUCTION_SECURITY_PROFILE", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "local")

    assert production_security_profile_enabled(service_name="unit service") is False


def test_production_security_profile_supports_explicit_opt_out(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LOTUS_CORE_PRODUCTION_SECURITY_PROFILE", "false")

    assert production_security_profile_enabled(service_name="unit service") is False
