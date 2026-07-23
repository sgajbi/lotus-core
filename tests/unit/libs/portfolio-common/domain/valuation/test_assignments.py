"""Tests for exact-scope, effective-dated valuation-policy assignments."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from portfolio_common.domain.valuation import (
    InstrumentValuationPolicyAssignment,
    MissingValuationPolicyAssignmentError,
    OverlappingValuationPolicyAssignmentError,
    ValuationPolicyAssignmentError,
    ValuationPolicyAssignmentStatus,
    resolve_valuation_policy_assignment,
    revaluation_start_for_assignment_correction,
    validate_no_overlapping_active_assignments,
)


def _assignment(**overrides: object) -> InstrumentValuationPolicyAssignment:
    values: dict[str, object] = {
        "tenant_id": "TENANT_SG",
        "legal_book_id": "BOOK_SG_PB",
        "security_id": "SEC_BOND_001",
        "policy_id": "BOND_CLEAN_PERCENT_OF_PAR",
        "policy_version": 2,
        "valid_from": date(2026, 1, 1),
        "valid_to": None,
        "assignment_status": ValuationPolicyAssignmentStatus.ACTIVE,
        "assignment_version": 1,
        "source_system": "security_master",
        "source_record_id": "SEC_BOND_001_VALUATION_POLICY",
        "source_revision": "revision-17",
        "observed_at": datetime(2026, 1, 1, 8, tzinfo=UTC),
        "assignment_reason": "Approved security-master valuation representation",
    }
    values.update(overrides)
    return InstrumentValuationPolicyAssignment(**values)  # type: ignore[arg-type]


def test_resolution_is_exact_scope_effective_dated_and_cache_complete() -> None:
    assignment = _assignment()

    resolved = resolve_valuation_policy_assignment(
        [assignment],
        tenant_id="TENANT_SG",
        legal_book_id="BOOK_SG_PB",
        security_id="SEC_BOND_001",
        valuation_date=date(2026, 7, 18),
    )

    assert resolved.assignment is assignment
    assert resolved.cache_key.tenant_id == "TENANT_SG"
    assert resolved.cache_key.legal_book_id == "BOOK_SG_PB"
    assert resolved.cache_key.security_id == "SEC_BOND_001"
    assert resolved.cache_key.valuation_date == date(2026, 7, 18)
    assert resolved.cache_key.policy_version == 2
    assert resolved.cache_key.assignment_version == 1
    assert resolved.cache_key.source_revision == "revision-17"
    assert len(resolved.cache_key.assignment_content_hash) == 64
    assert resolved.cache_key.assignment_content_hash == assignment.content_hash()


def test_assignment_hash_normalizes_equivalent_observation_instants() -> None:
    baseline = _assignment(observed_at=datetime(2026, 1, 1, 8, tzinfo=UTC))
    singapore = _assignment(
        observed_at=datetime(
            2026,
            1,
            1,
            16,
            tzinfo=timezone(timedelta(hours=8)),
        )
    )

    assert singapore.content_hash() == baseline.content_hash()


@pytest.mark.parametrize(
    ("tenant_id", "legal_book_id", "security_id"),
    [
        ("TENANT_HK", "BOOK_SG_PB", "SEC_BOND_001"),
        ("TENANT_SG", "BOOK_HK_PB", "SEC_BOND_001"),
        ("TENANT_SG", "BOOK_SG_PB", "SEC_BOND_999"),
    ],
)
def test_resolution_never_falls_back_across_tenant_book_or_instrument(
    tenant_id: str,
    legal_book_id: str,
    security_id: str,
) -> None:
    with pytest.raises(MissingValuationPolicyAssignmentError, match="exact tenant"):
        resolve_valuation_policy_assignment(
            [_assignment()],
            tenant_id=tenant_id,
            legal_book_id=legal_book_id,
            security_id=security_id,
            valuation_date=date(2026, 7, 18),
        )


def test_later_suspended_source_version_fences_older_active_assignment() -> None:
    active = _assignment()
    suspended = replace(
        active,
        assignment_status=ValuationPolicyAssignmentStatus.SUSPENDED,
        assignment_version=2,
        source_revision="revision-18",
        observed_at=datetime(2026, 7, 17, 8, tzinfo=UTC),
    )

    with pytest.raises(MissingValuationPolicyAssignmentError):
        resolve_valuation_policy_assignment(
            [active, suspended],
            tenant_id="TENANT_SG",
            legal_book_id="BOOK_SG_PB",
            security_id="SEC_BOND_001",
            valuation_date=date(2026, 7, 18),
        )


def test_conflicting_payloads_at_one_source_version_fail_closed() -> None:
    assignment = _assignment()
    conflicting = replace(
        assignment,
        policy_id="BOND_DIRTY_PERCENT_OF_PAR",
        source_revision="revision-conflict",
        observed_at=datetime(2026, 7, 18, 8, tzinfo=UTC),
    )

    with pytest.raises(ValuationPolicyAssignmentError, match="conflicting payloads"):
        resolve_valuation_policy_assignment(
            [assignment, conflicting],
            tenant_id="TENANT_SG",
            legal_book_id="BOOK_SG_PB",
            security_id="SEC_BOND_001",
            valuation_date=date(2026, 7, 18),
        )


def test_distinct_overlapping_source_records_fail_closed() -> None:
    first = _assignment()
    second = replace(
        first,
        policy_id="BOND_DIRTY_PERCENT_OF_PAR",
        source_record_id="SECOND_ASSIGNMENT",
        source_revision="revision-1",
    )

    with pytest.raises(OverlappingValuationPolicyAssignmentError, match="overlapping active"):
        resolve_valuation_policy_assignment(
            [first, second],
            tenant_id="TENANT_SG",
            legal_book_id="BOOK_SG_PB",
            security_id="SEC_BOND_001",
            valuation_date=date(2026, 7, 18),
        )
    with pytest.raises(OverlappingValuationPolicyAssignmentError, match="windows overlap"):
        validate_no_overlapping_active_assignments([first, second])


def test_adjacent_non_overlapping_assignments_are_valid() -> None:
    first = _assignment(valid_to=date(2026, 6, 30))
    second = replace(
        first,
        policy_id="BOND_DIRTY_PERCENT_OF_PAR",
        valid_from=date(2026, 7, 1),
        valid_to=None,
        source_record_id="SECOND_ASSIGNMENT",
        source_revision="revision-1",
    )

    validate_no_overlapping_active_assignments([first, second])
    resolved = resolve_valuation_policy_assignment(
        [first, second],
        tenant_id="TENANT_SG",
        legal_book_id="BOOK_SG_PB",
        security_id="SEC_BOND_001",
        valuation_date=date(2026, 7, 18),
    )
    assert resolved.assignment.policy_id == "BOND_DIRTY_PERCENT_OF_PAR"


def test_expired_assignment_fails_closed() -> None:
    with pytest.raises(MissingValuationPolicyAssignmentError):
        resolve_valuation_policy_assignment(
            [_assignment(valid_to=date(2026, 6, 30))],
            tenant_id="TENANT_SG",
            legal_book_id="BOOK_SG_PB",
            security_id="SEC_BOND_001",
            valuation_date=date(2026, 7, 18),
        )


def test_backdated_semantic_correction_returns_earliest_revaluation_date() -> None:
    previous = _assignment(valid_from=date(2026, 4, 1))
    current = replace(
        previous,
        policy_id="BOND_DIRTY_PERCENT_OF_PAR",
        valid_from=date(2026, 2, 1),
        assignment_version=2,
        source_revision="revision-18",
        observed_at=datetime(2026, 7, 18, 8, tzinfo=UTC),
    )

    assert revaluation_start_for_assignment_correction(previous, current) == date(2026, 2, 1)


def test_metadata_only_source_correction_does_not_request_revaluation() -> None:
    previous = _assignment()
    current = replace(
        previous,
        assignment_reason="Source metadata corrected without valuation-semantic change",
        assignment_version=2,
        source_revision="revision-18",
        observed_at=datetime(2026, 7, 18, 8, tzinfo=UTC),
    )

    assert revaluation_start_for_assignment_correction(previous, current) is None


def test_assignment_requires_aware_observation_and_valid_window() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _assignment(observed_at=datetime(2026, 7, 18, 8))
    with pytest.raises(ValueError, match="on or after"):
        _assignment(valid_from=date(2026, 7, 2), valid_to=date(2026, 7, 1))


@pytest.mark.parametrize("assignment_version", [True, Decimal("1"), "1"])
def test_assignment_rejects_non_integer_source_version(assignment_version: object) -> None:
    with pytest.raises(TypeError, match="assignment_version must be an integer"):
        _assignment(assignment_version=assignment_version)
