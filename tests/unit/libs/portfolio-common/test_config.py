import importlib
import logging

from portfolio_common.config import (
    _coerce_consumer_config_value,
    _env_bool,
    _env_int,
    _sanitize_consumer_override_map,
    _validate_consumer_override_relationships,
    get_kafka_consumer_runtime_overrides,
)


def test_rejects_invalid_auto_offset_reset_value():
    sanitized = _sanitize_consumer_override_map(
        {"auto.offset.reset": "middle"},
        context="test",
    )

    assert sanitized == {}


def test_normalizes_valid_auto_offset_reset_value():
    sanitized = _sanitize_consumer_override_map(
        {"auto.offset.reset": "LATEST"},
        context="test",
    )

    assert sanitized["auto.offset.reset"] == "latest"


def test_rejects_boolean_for_integer_consumer_setting():
    sanitized = _sanitize_consumer_override_map(
        {"max.poll.interval.ms": True},
        context="test",
    )

    assert sanitized == {}


def test_accepts_integer_string_for_integer_consumer_setting():
    assert _coerce_consumer_config_value("max.poll.interval.ms", "180000") == 180000


def test_env_int_falls_back_for_invalid_value(caplog, monkeypatch):
    caplog.set_level(logging.WARNING)
    monkeypatch.setenv("TEST_INT_SETTING", "bad")

    assert _env_int("TEST_INT_SETTING", 7, minimum=0) == 7
    assert "falling back to default" in caplog.text


def test_env_int_falls_back_for_out_of_range_value(caplog, monkeypatch):
    caplog.set_level(logging.WARNING)
    monkeypatch.setenv("TEST_INT_SETTING", "-1")

    assert _env_int("TEST_INT_SETTING", 7, minimum=0) == 7
    assert "falling back to default" in caplog.text


def test_env_bool_accepts_true_variants(monkeypatch):
    monkeypatch.setenv("TEST_BOOL_SETTING", "YES")

    assert _env_bool("TEST_BOOL_SETTING", False) is True


def test_env_bool_falls_back_for_invalid_value(caplog, monkeypatch):
    caplog.set_level(logging.WARNING)
    monkeypatch.setenv("TEST_BOOL_SETTING", "maybe")

    assert _env_bool("TEST_BOOL_SETTING", False) is False
    assert "falling back to default" in caplog.text


def test_rejects_non_positive_integer_consumer_setting():
    sanitized = _sanitize_consumer_override_map(
        {"session.timeout.ms": 0},
        context="test",
    )

    assert sanitized == {}


def test_drops_invalid_heartbeat_session_relationship():
    validated = _validate_consumer_override_relationships(
        {
            "session.timeout.ms": 30000,
            "heartbeat.interval.ms": 30000,
        },
        context="test",
    )

    assert validated == {"session.timeout.ms": 30000}


def test_group_override_drops_invalid_heartbeat_session_relationship(monkeypatch):
    monkeypatch.setenv(
        "LOTUS_CORE_KAFKA_CONSUMER_GROUP_OVERRIDES_JSON",
        '{"test-group": {"session.timeout.ms": 30000, "heartbeat.interval.ms": 30000}}',
    )

    overrides = get_kafka_consumer_runtime_overrides("test-group")

    assert overrides == {"session.timeout.ms": 30000}


def test_merged_defaults_and_group_overrides_drop_invalid_heartbeat_session_relationship(
    monkeypatch,
):
    monkeypatch.setenv(
        "LOTUS_CORE_KAFKA_CONSUMER_DEFAULTS_JSON",
        '{"session.timeout.ms": 30000}',
    )
    monkeypatch.setenv(
        "LOTUS_CORE_KAFKA_CONSUMER_GROUP_OVERRIDES_JSON",
        '{"test-group": {"heartbeat.interval.ms": 30000}}',
    )

    overrides = get_kafka_consumer_runtime_overrides("test-group")

    assert overrides == {"session.timeout.ms": 30000}


def test_business_date_guardrail_invalid_env_does_not_break_import(monkeypatch):
    monkeypatch.setenv("BUSINESS_DATE_MAX_FUTURE_DAYS", "invalid")
    monkeypatch.setenv("CASHFLOW_RULE_CACHE_TTL_SECONDS", "0")
    monkeypatch.setenv("BUSINESS_DATE_ENFORCE_MONOTONIC_ADVANCE", "maybe")

    import portfolio_common.config as config_module

    reloaded = importlib.reload(config_module)

    assert reloaded.BUSINESS_DATE_MAX_FUTURE_DAYS == 0
    assert reloaded.CASHFLOW_RULE_CACHE_TTL_SECONDS == 300
    assert reloaded.BUSINESS_DATE_ENFORCE_MONOTONIC_ADVANCE is False
