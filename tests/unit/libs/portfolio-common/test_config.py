from portfolio_common.config import (
    _coerce_consumer_config_value,
    _sanitize_consumer_override_map,
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
