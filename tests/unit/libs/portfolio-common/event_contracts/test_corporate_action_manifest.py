"""Prove deterministic corporate-action manifest transport authority."""

from copy import deepcopy

import pytest
from portfolio_common.event_contracts import CorporateActionManifestReceivedEvent
from pydantic import ValidationError


def _event() -> dict[str, object]:
    return {
        "event_type": "corporate_action.manifest.received",
        "schema_version": "1.0.0",
        "corporate_action_event_id": " EVENT_001 ",
        "portfolio_id": " PORTFOLIO_001 ",
        "linked_transaction_group_id": " GROUP_001 ",
        "parent_event_reference": " PARENT_001 ",
        "corporate_action_type": " spin_off ",
        "version": 1,
        "completion_declared": True,
        "expected_children": [
            {
                "transaction_id": " TX_TARGET ",
                "transaction_type": " spin_in ",
                "child_role": " target_position_add ",
                "dependency_transaction_ids": [" TX_SOURCE "],
                "child_sequence_hint": 2,
                "instrument_id": "SECURITY_TARGET",
                "source_instrument_id": "SECURITY_SOURCE",
                "target_instrument_id": "SECURITY_TARGET",
            },
            {
                "transaction_id": " TX_SOURCE ",
                "transaction_type": " spin_off ",
                "child_role": " source_position_reduce ",
                "dependency_transaction_ids": [],
                "child_sequence_hint": 1,
                "instrument_id": "SECURITY_SOURCE",
                "source_instrument_id": "SECURITY_SOURCE",
                "target_instrument_id": "SECURITY_TARGET",
            },
        ],
        "source": {
            "source_system": " corporate-actions-master ",
            "source_record_id": " EVENT_001 ",
            "source_revision": " revision-1 ",
            "source_content_hash": "a" * 64,
            "observed_at": "2026-08-11T10:15:00+08:00",
        },
    }


def test_event_normalizes_authority_and_uses_group_partition_key() -> None:
    event = CorporateActionManifestReceivedEvent.model_validate(_event())

    assert event.corporate_action_type == "SPIN_OFF"
    assert event.expected_children[0].transaction_type == "SPIN_IN"
    assert event.expected_children[0].dependency_transaction_ids == ("TX_SOURCE",)
    assert event.partition_key == "PORTFOLIO_001|transaction-group|GROUP_001"
    assert len(event.content_hash()) == 64
    assert event.source.observed_at.isoformat() == "2026-08-11T02:15:00+00:00"


def test_event_hash_is_stable_for_semantically_identical_child_order() -> None:
    first = CorporateActionManifestReceivedEvent.model_validate(_event())
    reordered = _event()
    children = reordered["expected_children"]
    assert isinstance(children, list)
    children.reverse()
    second = CorporateActionManifestReceivedEvent.model_validate(reordered)

    assert first.content_hash() == second.content_hash()


@pytest.mark.parametrize(
    ("path", "replacement"),
    (
        (("source", "source_revision"), "revision-2"),
        (("expected_children", 0, "transaction_id"), "TX_OTHER"),
        (("expected_children", 0, "dependency_transaction_ids"), []),
        (("completion_declared",), False),
    ),
)
def test_event_hash_changes_when_source_or_manifest_authority_changes(
    path: tuple[str | int, ...], replacement: object
) -> None:
    baseline_payload = _event()
    changed_payload = deepcopy(baseline_payload)
    target: object = changed_payload
    for component in path[:-1]:
        assert isinstance(target, (dict, list))
        target = target[component]  # type: ignore[index]
    assert isinstance(target, (dict, list))
    target[path[-1]] = replacement  # type: ignore[index]

    baseline = CorporateActionManifestReceivedEvent.model_validate(baseline_payload)
    changed = CorporateActionManifestReceivedEvent.model_validate(changed_payload)
    assert baseline.content_hash() != changed.content_hash()


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("version", 0),
        ("version", True),
        ("completion_declared", 1),
    ),
)
def test_event_rejects_non_contractual_version_and_completion_values(
    field: str, value: object
) -> None:
    payload = _event()
    payload[field] = value

    with pytest.raises(ValidationError):
        CorporateActionManifestReceivedEvent.model_validate(payload)


@pytest.mark.parametrize("observed_at", ("2026-08-11T10:15:00", 123))
def test_event_rejects_unqualified_source_observation_time(observed_at: object) -> None:
    payload = _event()
    source = payload["source"]
    assert isinstance(source, dict)
    source["observed_at"] = observed_at

    with pytest.raises(ValidationError):
        CorporateActionManifestReceivedEvent.model_validate(payload)


def test_event_rejects_missing_or_malformed_source_hash() -> None:
    for source_hash in ("", "sha256:" + "a" * 64, "A" * 64):
        payload = _event()
        source = payload["source"]
        assert isinstance(source, dict)
        source["source_content_hash"] = source_hash

        with pytest.raises(ValidationError):
            CorporateActionManifestReceivedEvent.model_validate(payload)


def test_event_rejects_unknown_fields() -> None:
    payload = _event()
    payload["synthetic_authority"] = True

    with pytest.raises(ValidationError):
        CorporateActionManifestReceivedEvent.model_validate(payload)
