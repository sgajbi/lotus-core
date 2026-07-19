from __future__ import annotations

from copy import deepcopy

import pytest
from portfolio_common.domain.valuation.assignments import ValuationPolicyAssignmentStatus
from pydantic import ValidationError

from src.services.ingestion_service.app.DTOs.reference_data_dto import (
    InstrumentValuationPolicyAssignmentIngestionRequest,
    InstrumentValuationPolicyAssignmentRecord,
)


def _assignment(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "tenant_id": " LOTUS_PB_SG ",
        "legal_book_id": " SG_PRIVATE_BANK_BOOK ",
        "security_id": " BOND_US_CORP_2031 ",
        "policy_id": " CLEAN_PERCENT_FACE_CALCULATED_ACCRUAL ",
        "policy_version": 1,
        "valid_from": "2026-01-01",
        "valid_to": "2026-12-31",
        "assignment_status": "ACTIVE",
        "assignment_version": 1,
        "source_system": " security_master ",
        "source_record_id": " VALPOL-BOND_US_CORP_2031-SG ",
        "source_revision": " rev-001 ",
        "observed_at": "2026-01-02T08:00:00+08:00",
        "assignment_reason": " Clean-price fixed-rate bond treatment. ",
    }
    record.update(overrides)
    return record


def test_valuation_policy_assignment_normalizes_and_validates_governed_policy() -> None:
    assignment = InstrumentValuationPolicyAssignmentRecord.model_validate(_assignment())

    assert assignment.tenant_id == "LOTUS_PB_SG"
    assert assignment.legal_book_id == "SG_PRIVATE_BANK_BOOK"
    assert assignment.security_id == "BOND_US_CORP_2031"
    assert assignment.assignment_status is ValuationPolicyAssignmentStatus.ACTIVE
    assert assignment.source_revision == "rev-001"
    assert assignment.to_domain().content_hash()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("legal_book_id", "   ", "must not be blank"),
        ("observed_at", "2026-01-02T08:00:00", "timezone offset"),
        ("valid_to", "2025-12-31", "on or after valid_from"),
        ("policy_id", "UNSUPPORTED_PRODUCT_DEFAULT", "unsupported valuation policy"),
        ("policy_version", 2, "unsupported valuation policy"),
        ("assignment_status", "PENDING", "Input should be 'ACTIVE'"),
    ],
)
def test_valuation_policy_assignment_rejects_unsafe_authority(
    field: str, value: object, message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        InstrumentValuationPolicyAssignmentRecord.model_validate(_assignment(**{field: value}))


def test_valuation_policy_assignment_batch_rejects_duplicate_source_version() -> None:
    duplicate = _assignment()

    with pytest.raises(ValidationError, match="duplicate source-version identities"):
        InstrumentValuationPolicyAssignmentIngestionRequest.model_validate(
            {"valuation_policy_assignments": [duplicate, deepcopy(duplicate)]}
        )


def test_valuation_policy_assignment_requires_explicit_lifecycle_state() -> None:
    record = _assignment()
    record.pop("assignment_status")

    with pytest.raises(ValidationError, match="Field required"):
        InstrumentValuationPolicyAssignmentRecord.model_validate(record)


def test_valuation_policy_assignment_batch_accepts_non_overlapping_correction_history() -> None:
    request = InstrumentValuationPolicyAssignmentIngestionRequest.model_validate(
        {
            "valuation_policy_assignments": [
                _assignment(valid_to="2026-03-31"),
                _assignment(
                    source_record_id="VALPOL-BOND_US_CORP_2031-SG-SECOND",
                    source_revision="rev-002",
                    valid_from="2026-04-01",
                    valid_to=None,
                ),
            ]
        }
    )

    assert len(request.valuation_policy_assignments) == 2


def test_valuation_policy_assignment_batch_rejects_overlapping_active_sources() -> None:
    with pytest.raises(ValidationError, match="windows overlap"):
        InstrumentValuationPolicyAssignmentIngestionRequest.model_validate(
            {
                "valuation_policy_assignments": [
                    _assignment(valid_to=None),
                    _assignment(
                        source_record_id="VALPOL-BOND_US_CORP_2031-SG-SECOND",
                        source_revision="rev-002",
                        valid_from="2026-04-01",
                        valid_to=None,
                    ),
                ]
            }
        )


def test_valuation_policy_assignment_batch_ranks_latest_source_correction_before_overlap() -> None:
    request = InstrumentValuationPolicyAssignmentIngestionRequest.model_validate(
        {
            "valuation_policy_assignments": [
                _assignment(valid_to=None),
                _assignment(
                    assignment_version=2,
                    source_revision="rev-002",
                    assignment_status="RETIRED",
                    observed_at="2026-02-02T08:00:00+08:00",
                ),
                _assignment(
                    source_record_id="VALPOL-BOND_US_CORP_2031-SG-SECOND",
                    source_revision="rev-003",
                    valid_from="2026-04-01",
                    valid_to=None,
                ),
            ]
        }
    )

    assert [record.assignment_version for record in request.valuation_policy_assignments] == [
        1,
        2,
        1,
    ]
