"""Prove the correction-triggered fixed-income disposal replay contract."""

from __future__ import annotations

from copy import deepcopy

import pytest
from portfolio_common.event_contracts import (
    FixedIncomeBookCostDisposalReplayRequestedEvent,
)
from pydantic import ValidationError

_HASH_A = "a" * 64
_HASH_B = "b" * 64


def _event() -> dict[str, object]:
    return {
        "event_type": "fixed_income.book_cost.disposal_replay.requested",
        "schema_version": "1.0.0",
        "command_id": _HASH_A,
        "scope": {
            "tenant_id": " TENANT_001 ",
            "legal_book_id": " BOOK_001 ",
            "portfolio_id": " PORTFOLIO_001 ",
            "security_id": " SECURITY_001 ",
            "lot_id": " LOT_001 ",
        },
        "earliest_affected_date": "2026-01-01",
        "first_affected_transaction_id": " SELL_001 ",
        "first_affected_transaction_timestamp": "2026-03-01T17:30:00+08:00",
        "source_authority_event_content_hash": _HASH_B,
        "profile_decisions": [
            {
                "effective_date": "2026-01-01",
                "profile_id": " PROFILE_001 ",
                "profile_version": 2,
                "authority_content_hash": _HASH_B,
                "eligibility_reason": None,
            }
        ],
        "correlation_id": " correlation-1 ",
        "traceparent": " 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01 ",
    }


def test_replay_event_normalizes_scope_timestamp_and_diagnostics() -> None:
    event = FixedIncomeBookCostDisposalReplayRequestedEvent.model_validate(_event())

    assert event.partition_key == ("TENANT_001|BOOK_001|PORTFOLIO_001|SECURITY_001|LOT_001")
    assert event.first_affected_transaction_id == "SELL_001"
    assert event.first_affected_transaction_timestamp.isoformat() == ("2026-03-01T09:30:00+00:00")
    assert event.correlation_id == "correlation-1"
    assert event.profile_decisions[0].profile_id == "PROFILE_001"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("event_type", "fixed_income.book_cost.authority.received"),
        ("schema_version", "2.0.0"),
        ("command_id", "not-a-hash"),
        ("source_authority_event_content_hash", "not-a-hash"),
        ("first_affected_transaction_timestamp", "2026-03-01T09:30:00"),
    ),
)
def test_replay_event_rejects_wrong_or_malformed_contract_fields(
    field: str,
    value: object,
) -> None:
    payload = _event()
    payload[field] = value

    with pytest.raises(ValidationError):
        FixedIncomeBookCostDisposalReplayRequestedEvent.model_validate(payload)


def test_replay_event_rejects_noncanonical_or_duplicate_profile_decisions() -> None:
    later = {
        "effective_date": "2026-07-01",
        "profile_id": "PROFILE_002",
        "profile_version": 3,
        "authority_content_hash": _HASH_A,
        "eligibility_reason": "ASSIGNMENT_MISSING",
    }
    payload = _event()
    payload["profile_decisions"] = [later, *payload["profile_decisions"]]  # type: ignore[misc]

    with pytest.raises(ValidationError, match="canonical effective-date order"):
        FixedIncomeBookCostDisposalReplayRequestedEvent.model_validate(payload)

    duplicate = _event()
    duplicate["profile_decisions"] = [
        *duplicate["profile_decisions"],  # type: ignore[misc]
        {
            "effective_date": "2026-01-01",
            "profile_id": "PROFILE_002",
            "profile_version": 3,
            "authority_content_hash": _HASH_A,
            "eligibility_reason": None,
        },
    ]
    with pytest.raises(ValidationError, match="unique effective dates"):
        FixedIncomeBookCostDisposalReplayRequestedEvent.model_validate(duplicate)


def test_replay_event_rejects_anchor_before_affected_boundary_and_unknown_fields() -> None:
    before = _event()
    before["earliest_affected_date"] = "2026-04-01"
    with pytest.raises(ValidationError, match="cannot precede"):
        FixedIncomeBookCostDisposalReplayRequestedEvent.model_validate(before)

    extra = deepcopy(_event())
    extra["unexpected"] = "value"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        FixedIncomeBookCostDisposalReplayRequestedEvent.model_validate(extra)
