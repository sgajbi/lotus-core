from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from portfolio_common.domain.portfolio_party_roles import (
    PortfolioPartyRoleQualityStatus,
    PortfolioPartyRoleScope,
    PortfolioPartyRoleType,
)

from src.services.query_control_plane_service.app.application.portfolio_party_roles import (
    PortfolioPartyRoleAssignmentService,
)
from src.services.query_control_plane_service.app.contracts.portfolio_party_roles import (
    PortfolioPartyRoleAssignmentRequest,
)
from src.services.query_control_plane_service.app.domain.portfolio_party_roles import (
    PortfolioPartyRoleRecord,
)


class _Clock:
    def utc_now(self) -> datetime:
        return datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


class _Reader:
    def __init__(self, records: list[PortfolioPartyRoleRecord]) -> None:
        self.records = records
        self.call: dict[str, object] | None = None

    async def list_effective_assignments(self, **kwargs):  # type: ignore[no-untyped-def]
        self.call = kwargs
        return self.records


def _record(
    *,
    quality_status: PortfolioPartyRoleQualityStatus = PortfolioPartyRoleQualityStatus.ACCEPTED,
    source_record_id: str = "coverage-PB_SG_GLOBAL_BAL_001-PM-001",
) -> PortfolioPartyRoleRecord:
    return PortfolioPartyRoleRecord(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        party_id="PARTY_PM_SG_001",
        role_type=PortfolioPartyRoleType.DISCRETIONARY_PORTFOLIO_MANAGER,
        role_scope=PortfolioPartyRoleScope.PORTFOLIO_MANAGEMENT,
        effective_from=date(2026, 4, 1),
        effective_to=None,
        assignment_version=2,
        source_system="relationship_master",
        source_record_id=source_record_id,
        observed_at=datetime(2026, 7, 17, 9, 0, tzinfo=UTC),
        quality_status=quality_status,
        created_at=datetime(2026, 7, 17, 9, 1, tzinfo=UTC),
        updated_at=datetime(2026, 7, 17, 9, 2, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_party_role_service_preserves_governed_filters_and_lineage() -> None:
    reader = _Reader([_record()])
    request = PortfolioPartyRoleAssignmentRequest(
        as_of_date=date(2026, 7, 18),
        party_id="PARTY_PM_SG_001",
        role_types=[PortfolioPartyRoleType.DISCRETIONARY_PORTFOLIO_MANAGER],
        role_scopes=[PortfolioPartyRoleScope.PORTFOLIO_MANAGEMENT],
    )

    response = await PortfolioPartyRoleAssignmentService(reader=reader, clock=_Clock()).resolve(
        portfolio_id="PB_SG_GLOBAL_BAL_001", request=request
    )

    assert reader.call == {
        "portfolio_id": "PB_SG_GLOBAL_BAL_001",
        "as_of_date": date(2026, 7, 18),
        "party_id": "PARTY_PM_SG_001",
        "role_types": (PortfolioPartyRoleType.DISCRETIONARY_PORTFOLIO_MANAGER,),
        "role_scopes": (PortfolioPartyRoleScope.PORTFOLIO_MANAGEMENT,),
        "include_non_accepted": False,
    }
    assert response.supportability.state == "READY"
    assert response.supportability.reason == "PARTY_ROLE_ASSIGNMENTS_READY"
    assert response.data_quality_status == "COMPLETE"
    assert response.assignments[0].party_id == "PARTY_PM_SG_001"
    assert response.lineage["legacy_advisor_inference"] == "disabled"
    assert response.latest_evidence_timestamp == datetime(2026, 7, 17, 9, 2, tzinfo=UTC)


@pytest.mark.asyncio
async def test_party_role_service_returns_explicit_incomplete_empty_result() -> None:
    response = await PortfolioPartyRoleAssignmentService(
        reader=_Reader([]), clock=_Clock()
    ).resolve(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=PortfolioPartyRoleAssignmentRequest(as_of_date=date(2026, 7, 18)),
    )

    assert response.assignments == []
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "PARTY_ROLE_ASSIGNMENTS_EMPTY"
    assert response.data_quality_status == "MISSING"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "non_accepted_status",
    [
        PortfolioPartyRoleQualityStatus.PENDING_REVIEW,
        PortfolioPartyRoleQualityStatus.QUARANTINED,
        PortfolioPartyRoleQualityStatus.REJECTED,
    ],
)
async def test_party_role_service_does_not_overstate_nonaccepted_assignments(
    non_accepted_status: PortfolioPartyRoleQualityStatus,
) -> None:
    reader = _Reader(
        [
            _record(),
            _record(
                quality_status=non_accepted_status,
                source_record_id="coverage-PB_SG_GLOBAL_BAL_001-RM-001",
            ),
        ]
    )

    response = await PortfolioPartyRoleAssignmentService(reader=reader, clock=_Clock()).resolve(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=PortfolioPartyRoleAssignmentRequest(
            as_of_date=date(2026, 7, 18),
            include_non_accepted=True,
        ),
    )

    assert reader.call is not None
    assert reader.call["include_non_accepted"] is True
    assert response.data_quality_status == "PARTIAL"
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "PARTY_ROLE_ASSIGNMENTS_NON_ACCEPTED"
    assert [assignment.quality_status for assignment in response.assignments] == [
        PortfolioPartyRoleQualityStatus.ACCEPTED,
        non_accepted_status,
    ]
