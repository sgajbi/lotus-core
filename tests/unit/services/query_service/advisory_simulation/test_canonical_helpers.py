from src.services.query_service.app.advisory_simulation.common.canonical import (
    canonical_json,
    hash_canonical_payload,
    strip_keys,
)


def test_canonical_json_sorts_keys_and_removes_pretty_whitespace() -> None:
    payload = {"b": 1, "a": {"d": 4, "c": 3}}

    assert canonical_json(payload) == '{"a":{"c":3,"d":4},"b":1}'


def test_hash_canonical_payload_is_stable_for_equivalent_dict_order() -> None:
    left = {"a": 1, "b": {"c": 2, "d": 3}}
    right = {"b": {"d": 3, "c": 2}, "a": 1}

    assert hash_canonical_payload(left) == hash_canonical_payload(right)


def test_strip_keys_removes_nested_keys_without_mutating_source() -> None:
    payload = {
        "correlation_id": "corr_1",
        "nested": {"request_hash": "hash_1", "keep": True},
        "items": [{"request_hash": "hash_2", "value": 7}],
    }

    stripped = strip_keys(payload, exclude={"correlation_id", "request_hash"})

    assert stripped == {"nested": {"keep": True}, "items": [{"value": 7}]}
    assert payload["correlation_id"] == "corr_1"
    assert payload["nested"]["request_hash"] == "hash_1"
