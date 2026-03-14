from portfolio_common.config import (
    _coerce_consumer_config_value,
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
