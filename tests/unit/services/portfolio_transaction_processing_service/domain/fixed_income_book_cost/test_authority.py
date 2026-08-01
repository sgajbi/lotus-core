"""Tests for exact-scope source-lot amortized-cost policy authority."""

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from services.portfolio_transaction_processing_service.app.domain.fixed_income_book_cost import (
    AmortizedCostAssignmentStatus,
    AmortizedCostAuthorityError,
    LotAmortizedCostPolicyAssignment,
    LotBookCostAuthorityScope,
    MissingAmortizedCostAssignmentError,
    OverlappingAmortizedCostAssignmentError,
    amortization_replay_start_for_assignment_correction,
    resolve_amortized_cost_assignment,
    validate_no_overlapping_active_amortized_cost_assignments,
)


def _scope(**overrides: str) -> LotBookCostAuthorityScope:
    values = {
        "tenant_id": "TENANT_SG",
        "legal_book_id": "BOOK_SG_PB",
        "portfolio_id": "PORTFOLIO_001",
        "security_id": "SEC_BOND_001",
        "lot_id": "LOT_BUY_001",
    }
    values.update(overrides)
    return LotBookCostAuthorityScope(**values)


def _assignment(**overrides: object) -> LotAmortizedCostPolicyAssignment:
    values: dict[str, object] = {
        "scope": _scope(),
        "policy_id": "IFRS9_EIR_LOCAL",
        "policy_version": 2,
        "valid_from": date(2026, 1, 1),
        "valid_to": None,
        "assignment_status": AmortizedCostAssignmentStatus.ACTIVE,
        "assignment_version": 1,
        "source_system": "accounting_policy_master",
        "source_record_id": "LOT_BUY_001_BOOK_COST_POLICY",
        "source_revision": "revision-17",
        "observed_at": datetime(2026, 1, 1, 8, tzinfo=UTC),
        "assignment_reason": "Approved lot-level amortized-cost treatment",
    }
    values.update(overrides)
    return LotAmortizedCostPolicyAssignment(**values)  # type: ignore[arg-type]


def test_resolution_is_exact_scope_effective_dated_and_cache_complete() -> None:
    assignment = _assignment()

    resolved = resolve_amortized_cost_assignment(
        [assignment],
        scope=_scope(),
        effective_date=date(2026, 7, 18),
    )

    assert resolved.assignment is assignment
    assert resolved.cache_key.scope == _scope()
    assert resolved.cache_key.effective_date == date(2026, 7, 18)
    assert resolved.cache_key.policy_id == "IFRS9_EIR_LOCAL"
    assert resolved.cache_key.policy_version == 2
    assert resolved.cache_key.assignment_version == 1
    assert resolved.cache_key.source_revision == "revision-17"
    assert resolved.cache_key.assignment_content_hash == assignment.content_hash()
    assert assignment.source_reference().source_content_hash == assignment.content_hash()


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("tenant_id", "TENANT_HK"),
        ("legal_book_id", "BOOK_HK_PB"),
        ("portfolio_id", "PORTFOLIO_999"),
        ("security_id", "SEC_BOND_999"),
        ("lot_id", "LOT_BUY_999"),
    ],
)
def test_resolution_never_falls_back_across_authority_scope(
    field_name: str,
    value: str,
) -> None:
    with pytest.raises(MissingAmortizedCostAssignmentError, match="exact tenant"):
        resolve_amortized_cost_assignment(
            [_assignment()],
            scope=_scope(**{field_name: value}),
            effective_date=date(2026, 7, 18),
        )


def test_later_suspension_fences_older_active_source_version() -> None:
    active = _assignment()
    suspended = replace(
        active,
        assignment_status=AmortizedCostAssignmentStatus.SUSPENDED,
        assignment_version=2,
        source_revision="revision-18",
    )

    with pytest.raises(MissingAmortizedCostAssignmentError):
        resolve_amortized_cost_assignment(
            [active, suspended],
            scope=_scope(),
            effective_date=date(2026, 7, 18),
        )


def test_same_source_and_version_with_conflicting_payload_fails_closed() -> None:
    first = _assignment()
    conflicting = replace(first, policy_id="IFRS9_STRAIGHT_LINE_LOCAL")

    with pytest.raises(AmortizedCostAuthorityError, match="conflicting payloads"):
        resolve_amortized_cost_assignment(
            [first, conflicting],
            scope=_scope(),
            effective_date=date(2026, 7, 18),
        )


def test_distinct_source_records_with_overlapping_windows_fail_closed() -> None:
    first = _assignment()
    second = replace(
        first,
        source_record_id="SECOND_ASSIGNMENT",
        source_revision="revision-1",
    )

    with pytest.raises(OverlappingAmortizedCostAssignmentError, match="overlapping active"):
        resolve_amortized_cost_assignment(
            [first, second],
            scope=_scope(),
            effective_date=date(2026, 7, 18),
        )
    with pytest.raises(OverlappingAmortizedCostAssignmentError, match="windows overlap"):
        validate_no_overlapping_active_amortized_cost_assignments([first, second])


def test_adjacent_windows_are_valid_and_resolve_by_date() -> None:
    first = _assignment(valid_to=date(2026, 6, 30))
    second = replace(
        first,
        policy_id="IFRS9_STRAIGHT_LINE_LOCAL",
        valid_from=date(2026, 7, 1),
        valid_to=None,
        source_record_id="SECOND_ASSIGNMENT",
        source_revision="revision-1",
    )

    validate_no_overlapping_active_amortized_cost_assignments([first, second])

    resolved = resolve_amortized_cost_assignment(
        [first, second],
        scope=_scope(),
        effective_date=date(2026, 7, 18),
    )
    assert resolved.assignment is second


def test_semantic_correction_returns_earliest_bounded_replay_date() -> None:
    previous = _assignment(valid_from=date(2026, 4, 1))
    current = replace(
        previous,
        policy_id="IFRS9_STRAIGHT_LINE_LOCAL",
        valid_from=date(2026, 2, 1),
        assignment_version=2,
        source_revision="revision-18",
    )

    assert amortization_replay_start_for_assignment_correction(previous, current) == date(
        2026, 2, 1
    )


def test_metadata_only_correction_does_not_request_replay() -> None:
    previous = _assignment()
    current = replace(
        previous,
        assignment_reason="Corrected approval note",
        assignment_version=2,
        source_revision="revision-18",
    )

    assert amortization_replay_start_for_assignment_correction(previous, current) is None


def test_assignment_rejects_invalid_boundaries_and_untyped_values() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _assignment(observed_at=datetime(2026, 1, 1, 8))
    with pytest.raises(ValueError, match="on or after"):
        _assignment(valid_from=date(2026, 2, 1), valid_to=date(2026, 1, 31))
    with pytest.raises(TypeError, match="policy_version must be an integer"):
        _assignment(policy_version=True)
    with pytest.raises(TypeError, match="effective_date must be a date"):
        resolve_amortized_cost_assignment(
            [_assignment()],
            scope=_scope(),
            effective_date=datetime(2026, 7, 18, tzinfo=UTC),  # type: ignore[arg-type]
        )
