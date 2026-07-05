import importlib
import logging

import pytest
from portfolio_common.config import (
    _coerce_consumer_config_value,
    _env_bool,
    _env_int,
    _sanitize_consumer_override_map,
    _validate_consumer_override_relationships,
    get_kafka_consumer_runtime_overrides,
)
from portfolio_common.kafka_consumer_execution import (
    KafkaConsumerExecutionProfile,
    load_kafka_consumer_execution_profile,
)
from portfolio_common.runtime_settings import RuntimeConfigurationError


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


def test_accepts_boolean_string_for_boolean_consumer_setting():
    assert _coerce_consumer_config_value("enable.auto.commit", "off") is False


def test_rejects_non_string_consumer_string_setting():
    with pytest.raises(ValueError, match="Expected str"):
        _coerce_consumer_config_value("auto.offset.reset", 123)


def test_env_int_falls_back_for_invalid_value(caplog, monkeypatch):
    caplog.set_level(logging.WARNING)
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.delenv("LOTUS_CORE_STRICT_CONFIG_VALIDATION", raising=False)
    monkeypatch.setenv("TEST_INT_SETTING", "bad")

    assert _env_int("TEST_INT_SETTING", 7, minimum=0) == 7
    assert "falling back to default" in caplog.text


def test_env_int_falls_back_for_out_of_range_value(caplog, monkeypatch):
    caplog.set_level(logging.WARNING)
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.delenv("LOTUS_CORE_STRICT_CONFIG_VALIDATION", raising=False)
    monkeypatch.setenv("TEST_INT_SETTING", "-1")

    assert _env_int("TEST_INT_SETTING", 7, minimum=0) == 7
    assert "falling back to default" in caplog.text


def test_env_int_strict_profile_rejects_invalid_value(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TEST_INT_SETTING", "bad")

    with pytest.raises(RuntimeConfigurationError, match="TEST_INT_SETTING"):
        _env_int("TEST_INT_SETTING", 7, minimum=0)


def test_env_bool_accepts_true_variants(monkeypatch):
    monkeypatch.setenv("TEST_BOOL_SETTING", "YES")

    assert _env_bool("TEST_BOOL_SETTING", False) is True


def test_env_bool_falls_back_for_invalid_value(caplog, monkeypatch):
    caplog.set_level(logging.WARNING)
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.delenv("LOTUS_CORE_STRICT_CONFIG_VALIDATION", raising=False)
    monkeypatch.setenv("TEST_BOOL_SETTING", "maybe")

    assert _env_bool("TEST_BOOL_SETTING", False) is False
    assert "falling back to default" in caplog.text


def test_env_bool_strict_profile_rejects_invalid_value(monkeypatch):
    monkeypatch.setenv("LOTUS_CORE_STRICT_CONFIG_VALIDATION", "true")
    monkeypatch.setenv("TEST_BOOL_SETTING", "maybe")

    with pytest.raises(RuntimeConfigurationError, match="TEST_BOOL_SETTING"):
        _env_bool("TEST_BOOL_SETTING", False)


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


def test_consumer_defaults_json_local_profile_ignores_invalid_json(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.delenv("LOTUS_CORE_STRICT_CONFIG_VALIDATION", raising=False)
    monkeypatch.setenv("LOTUS_CORE_KAFKA_CONSUMER_DEFAULTS_JSON", "{not-json")

    assert get_kafka_consumer_runtime_overrides("test-group") == {}


def test_consumer_defaults_json_strict_profile_rejects_invalid_json(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LOTUS_CORE_KAFKA_CONSUMER_DEFAULTS_JSON", "{not-json")

    with pytest.raises(
        RuntimeConfigurationError,
        match="LOTUS_CORE_KAFKA_CONSUMER_DEFAULTS_JSON",
    ):
        get_kafka_consumer_runtime_overrides("test-group")


def test_consumer_group_overrides_json_strict_profile_rejects_non_object(monkeypatch):
    monkeypatch.setenv("LOTUS_CORE_STRICT_CONFIG_VALIDATION", "true")
    monkeypatch.setenv("LOTUS_CORE_KAFKA_CONSUMER_GROUP_OVERRIDES_JSON", "[]")

    with pytest.raises(
        RuntimeConfigurationError,
        match="LOTUS_CORE_KAFKA_CONSUMER_GROUP_OVERRIDES_JSON",
    ):
        get_kafka_consumer_runtime_overrides("test-group")


def test_business_date_guardrail_invalid_env_does_not_break_import(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.delenv("LOTUS_CORE_STRICT_CONFIG_VALIDATION", raising=False)
    monkeypatch.setenv("BUSINESS_DATE_MAX_FUTURE_DAYS", "invalid")
    monkeypatch.setenv("CASHFLOW_RULE_CACHE_TTL_SECONDS", "0")
    monkeypatch.setenv("BUSINESS_DATE_ENFORCE_MONOTONIC_ADVANCE", "maybe")

    import portfolio_common.config as config_module

    reloaded = importlib.reload(config_module)

    assert reloaded.BUSINESS_DATE_MAX_FUTURE_DAYS == 0
    assert reloaded.CASHFLOW_RULE_CACHE_TTL_SECONDS == 300
    assert reloaded.BUSINESS_DATE_ENFORCE_MONOTONIC_ADVANCE is False


def test_business_date_guardrail_strict_profile_rejects_invalid_env(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("BUSINESS_DATE_MAX_FUTURE_DAYS", "invalid")

    import portfolio_common.config as config_module

    with pytest.raises(RuntimeConfigurationError, match="BUSINESS_DATE_MAX_FUTURE_DAYS"):
        importlib.reload(config_module)
    monkeypatch.delenv("BUSINESS_DATE_MAX_FUTURE_DAYS")
    importlib.reload(config_module)


def test_cashflow_cache_ttl_strict_profile_rejects_non_positive_env(monkeypatch):
    monkeypatch.setenv("LOTUS_CORE_STRICT_CONFIG_VALIDATION", "true")
    monkeypatch.setenv("CASHFLOW_RULE_CACHE_TTL_SECONDS", "0")

    import portfolio_common.config as config_module

    with pytest.raises(RuntimeConfigurationError, match="CASHFLOW_RULE_CACHE_TTL_SECONDS"):
        importlib.reload(config_module)
    monkeypatch.delenv("CASHFLOW_RULE_CACHE_TTL_SECONDS")
    importlib.reload(config_module)


def test_dlq_failure_budget_env_is_non_negative(monkeypatch):
    monkeypatch.setenv("KAFKA_CONSUMER_DLQ_FAILURE_MAX_ATTEMPTS", "3")

    import portfolio_common.config as config_module

    reloaded = importlib.reload(config_module)

    assert reloaded.KAFKA_CONSUMER_DLQ_FAILURE_MAX_ATTEMPTS == 3
    monkeypatch.delenv("KAFKA_CONSUMER_DLQ_FAILURE_MAX_ATTEMPTS")
    importlib.reload(config_module)


def test_invalid_dlq_failure_budget_falls_back_to_disabled(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.delenv("LOTUS_CORE_STRICT_CONFIG_VALIDATION", raising=False)
    monkeypatch.setenv("KAFKA_CONSUMER_DLQ_FAILURE_MAX_ATTEMPTS", "-1")

    import portfolio_common.config as config_module

    reloaded = importlib.reload(config_module)

    assert reloaded.KAFKA_CONSUMER_DLQ_FAILURE_MAX_ATTEMPTS == 0
    monkeypatch.delenv("KAFKA_CONSUMER_DLQ_FAILURE_MAX_ATTEMPTS")
    importlib.reload(config_module)


def test_retryable_failure_budget_env_values_are_non_negative(monkeypatch):
    monkeypatch.setenv("KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ATTEMPTS", "4")
    monkeypatch.setenv("KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ELAPSED_SECONDS", "900")

    import portfolio_common.config as config_module

    reloaded = importlib.reload(config_module)

    assert reloaded.KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ATTEMPTS == 4
    assert reloaded.KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ELAPSED_SECONDS == 900
    monkeypatch.delenv("KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ATTEMPTS")
    monkeypatch.delenv("KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ELAPSED_SECONDS")
    importlib.reload(config_module)


def test_invalid_retryable_failure_budget_values_fall_back_to_disabled(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.delenv("LOTUS_CORE_STRICT_CONFIG_VALIDATION", raising=False)
    monkeypatch.setenv("KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ATTEMPTS", "-1")
    monkeypatch.setenv("KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ELAPSED_SECONDS", "bad")

    import portfolio_common.config as config_module

    reloaded = importlib.reload(config_module)

    assert reloaded.KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ATTEMPTS == 0
    assert reloaded.KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ELAPSED_SECONDS == 0
    monkeypatch.delenv("KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ATTEMPTS")
    monkeypatch.delenv("KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ELAPSED_SECONDS")
    importlib.reload(config_module)


def test_kafka_retryable_failure_budget_strict_profile_rejects_invalid_env(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ELAPSED_SECONDS", "bad")

    import portfolio_common.config as config_module

    with pytest.raises(
        RuntimeConfigurationError,
        match="KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ELAPSED_SECONDS",
    ):
        importlib.reload(config_module)
    monkeypatch.delenv("KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ELAPSED_SECONDS")
    importlib.reload(config_module)


def test_kafka_consumer_execution_profile_defaults_preserve_serial_behavior(monkeypatch):
    monkeypatch.delenv("LOTUS_CORE_KAFKA_CONSUMER_EXECUTION_DEFAULTS_JSON", raising=False)
    monkeypatch.delenv("LOTUS_CORE_KAFKA_CONSUMER_EXECUTION_GROUP_OVERRIDES_JSON", raising=False)

    profile = load_kafka_consumer_execution_profile("test-group")

    assert profile == KafkaConsumerExecutionProfile()
    assert profile.poll_timeout_seconds == 1.0
    assert profile.max_in_flight_messages == 1
    assert profile.ordering_key == "partition"
    assert profile.per_key_concurrency == 1


def test_kafka_consumer_execution_profile_merges_group_override(monkeypatch):
    monkeypatch.setenv(
        "LOTUS_CORE_KAFKA_CONSUMER_EXECUTION_DEFAULTS_JSON",
        '{"poll_timeout_seconds": 0.5, "shutdown_drain_timeout_seconds": 15}',
    )
    monkeypatch.setenv(
        "LOTUS_CORE_KAFKA_CONSUMER_EXECUTION_GROUP_OVERRIDES_JSON",
        '{"test-group": {"max_in_flight_messages": 2}}',
    )

    profile = load_kafka_consumer_execution_profile("test-group")

    assert profile.poll_timeout_seconds == 0.5
    assert profile.max_in_flight_messages == 2
    assert profile.shutdown_drain_timeout_seconds == 15
    assert profile.ordering_key == "partition"


def test_kafka_consumer_execution_profile_local_invalid_falls_back(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.delenv("LOTUS_CORE_STRICT_CONFIG_VALIDATION", raising=False)
    monkeypatch.setenv(
        "LOTUS_CORE_KAFKA_CONSUMER_EXECUTION_DEFAULTS_JSON",
        '{"poll_timeout_seconds": 0}',
    )

    profile = load_kafka_consumer_execution_profile("test-group")

    assert profile == KafkaConsumerExecutionProfile()


def test_kafka_consumer_execution_profile_strict_rejects_invalid(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv(
        "LOTUS_CORE_KAFKA_CONSUMER_EXECUTION_DEFAULTS_JSON",
        '{"per_key_concurrency": 2}',
    )

    with pytest.raises(
        RuntimeConfigurationError,
        match="LOTUS_CORE_KAFKA_CONSUMER_EXECUTION_DEFAULTS_JSON",
    ):
        load_kafka_consumer_execution_profile("test-group")


def test_canonical_topic_env_overrides_default_runtime_name(monkeypatch):
    monkeypatch.setenv("KAFKA_TRANSACTIONS_PERSISTED_TOPIC", "custom.transactions.persisted")

    import portfolio_common.config as config_module

    reloaded = importlib.reload(config_module)

    assert reloaded.KAFKA_TRANSACTIONS_PERSISTED_TOPIC == "custom.transactions.persisted"


def test_canonical_topic_defaults_match_rfc_runtime_names(monkeypatch):
    monkeypatch.delenv("KAFKA_VALUATION_JOB_REQUESTED_TOPIC", raising=False)
    monkeypatch.delenv("KAFKA_TRANSACTIONS_PERSISTED_TOPIC", raising=False)

    import portfolio_common.config as config_module

    reloaded = importlib.reload(config_module)

    assert reloaded.KAFKA_VALUATION_JOB_REQUESTED_TOPIC == "valuation.job.requested"
    assert reloaded.KAFKA_TRANSACTIONS_PERSISTED_TOPIC == "transactions.persisted"


def test_topic_registry_limits_runtime_names_to_active_topics():
    import portfolio_common.config as config_module

    statuses = {topic.lifecycle_status for topic in config_module.KAFKA_TOPIC_DEFINITIONS}
    runtime_names = set(config_module.KAFKA_TOPIC_RUNTIME_NAMES)
    inactive_names = {
        topic.runtime_name
        for topic in config_module.KAFKA_TOPIC_DEFINITIONS
        if topic.lifecycle_status == "inactive"
    }

    assert {"active", "inactive"} <= statuses
    assert config_module.KAFKA_TRANSACTIONS_PERSISTED_TOPIC in runtime_names
    assert inactive_names.isdisjoint(runtime_names)
