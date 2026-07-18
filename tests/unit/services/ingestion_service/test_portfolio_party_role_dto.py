from __future__ import annotations

import pytest
from portfolio_common.domain.portfolio_party_roles import (
    PortfolioPartyRoleQualityStatus,
    PortfolioPartyRoleScope,
    PortfolioPartyRoleType,
)
from pydantic import ValidationError

from src.services.ingestion_service.app.DTOs.reference_data_dto import (
    PortfolioPartyRoleAssignmentIngestionRequest,
    PortfolioPartyRoleAssignmentRecord,
)


def _assignment(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "portfolio_id": "PB_SG_GLOBAL_BAL_001",
        "party_id": "PARTY_PM_SG_001",
        "role_type": "discretionary_portfolio_manager",
        "role_scope": "portfolio_management",
        "effective_from": "2026-04-01",
        "assignment_version": 1,
        "source_system": "relationship_master",
        "source_record_id": "coverage-PB_SG_GLOBAL_BAL_001-PM-001",
        "observed_at": "2026-04-01T09:00:00+08:00",
        "quality_status": "accepted",
    }
    record.update(overrides)
    return record


def test_portfolio_party_role_assignment_parses_governed_source_truth() -> None:
    assignment = PortfolioPartyRoleAssignmentRecord.model_validate(_assignment())

    assert assignment.role_type is PortfolioPartyRoleType.DISCRETIONARY_PORTFOLIO_MANAGER
    assert assignment.role_scope is PortfolioPartyRoleScope.PORTFOLIO_MANAGEMENT
    assert assignment.quality_status is PortfolioPartyRoleQualityStatus.ACCEPTED
    assert assignment.observed_at.utcoffset() is not None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("role_type", "advisor"),
        ("role_scope", "all_responsibilities"),
        ("quality_status", "good"),
    ],
)
def test_portfolio_party_role_assignment_rejects_ungoverned_vocabulary(
    field: str, value: str
) -> None:
    with pytest.raises(ValidationError):
        PortfolioPartyRoleAssignmentRecord.model_validate(_assignment(**{field: value}))


def test_portfolio_party_role_assignment_rejects_invalid_interval_and_naive_observation() -> None:
    with pytest.raises(ValidationError, match="effective_to must be on or after"):
        PortfolioPartyRoleAssignmentRecord.model_validate(
            _assignment(effective_from="2026-04-10", effective_to="2026-04-01")
        )

    with pytest.raises(ValidationError, match="observed_at must include a timezone offset"):
        PortfolioPartyRoleAssignmentRecord.model_validate(
            _assignment(observed_at="2026-04-01T09:00:00")
        )


def test_portfolio_party_role_ingestion_rejects_duplicate_source_identity() -> None:
    duplicate = _assignment()

    with pytest.raises(ValidationError, match="duplicate source identities"):
        PortfolioPartyRoleAssignmentIngestionRequest.model_validate(
            {"party_role_assignments": [duplicate, dict(duplicate)]}
        )


def test_portfolio_party_role_ingestion_accepts_versioned_source_corrections() -> None:
    request = PortfolioPartyRoleAssignmentIngestionRequest.model_validate(
        {
            "party_role_assignments": [
                _assignment(assignment_version=1),
                _assignment(assignment_version=2, effective_to="2026-12-31"),
            ]
        }
    )

    assert [item.assignment_version for item in request.party_role_assignments] == [1, 2]
