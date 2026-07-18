"""Behavior tests for QCP-owned portfolio-manager book membership."""

from datetime import UTC, date, datetime
from typing import Literal

import pytest
from portfolio_common.domain.portfolio_party_roles import PortfolioPartyRoleType

from src.services.query_control_plane_service.app.application.portfolio_manager_book import (
    PortfolioManagerBookService,
)
from src.services.query_control_plane_service.app.contracts.portfolio_manager_book import (
    PortfolioManagerBookMembershipRequest,
)
from src.services.query_control_plane_service.app.domain.portfolio_manager_book import (
    PortfolioManagerBookRecord,
)


class _Clock:
    def utc_now(self) -> datetime:
        return datetime(2026, 5, 3, 10, tzinfo=UTC)


class _Reader:
    def __init__(self, records: list[PortfolioManagerBookRecord]) -> None:
        self.records = records
        self.calls: list[dict[str, object]] = []

    async def list_members(self, **kwargs):
        self.calls.append(kwargs)
        return self.records


def _record(
    *,
    membership_source: Literal[
        "party_role_assignment", "legacy_advisor_projection"
    ] = "legacy_advisor_projection",
    source_record_id: str | None = None,
) -> PortfolioManagerBookRecord:
    return PortfolioManagerBookRecord(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        client_id="CIF_SG_GLOBAL_BAL_001",
        booking_center_code="Singapore",
        portfolio_type="DISCRETIONARY",
        status="ACTIVE",
        open_date=date(2025, 3, 31),
        close_date=None,
        base_currency="SGD",
        created_at=datetime(2026, 5, 3, 8, tzinfo=UTC),
        updated_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
        membership_source=membership_source,
        role_type=(
            PortfolioPartyRoleType.DISCRETIONARY_PORTFOLIO_MANAGER
            if membership_source == "party_role_assignment"
            else None
        ),
        source_system=(
            "relationship_master" if membership_source == "party_role_assignment" else None
        ),
        source_record_id=source_record_id
        or (
            "coverage-PB_SG_GLOBAL_BAL_001-PM-001"
            if membership_source == "party_role_assignment"
            else None
        ),
        observed_at=(
            datetime(2026, 5, 3, 9, 30, tzinfo=UTC)
            if membership_source == "party_role_assignment"
            else None
        ),
    )


@pytest.mark.asyncio
async def test_resolves_effective_membership_with_deterministic_source_evidence() -> None:
    reader = _Reader([_record()])
    service = PortfolioManagerBookService(reader=reader, clock=_Clock())
    request = PortfolioManagerBookMembershipRequest(
        as_of_date=date(2026, 5, 3),
        booking_center_code="Singapore",
        portfolio_types=[" discretionary ", "", "advisory"],
    )

    first = await service.resolve_membership(portfolio_manager_id="PM_SG_DPM_001", request=request)
    second = await service.resolve_membership(portfolio_manager_id="PM_SG_DPM_001", request=request)

    assert first.members[0].portfolio_id == "PB_SG_GLOBAL_BAL_001"
    assert first.members[0].source_record_id == "portfolio:PB_SG_GLOBAL_BAL_001"
    assert first.supportability.state == "READY"
    assert first.data_quality_status == "ACCEPTED"
    assert first.generated_at == datetime(2026, 5, 3, 10, tzinfo=UTC)
    assert first.latest_evidence_timestamp == datetime(2026, 5, 3, 9, tzinfo=UTC)
    assert first.snapshot_id == second.snapshot_id
    assert reader.calls[0] == {
        "portfolio_manager_id": "PM_SG_DPM_001",
        "as_of_date": date(2026, 5, 3),
        "booking_center_code": "Singapore",
        "portfolio_types": ("DISCRETIONARY", "ADVISORY"),
        "include_inactive": False,
    }


@pytest.mark.asyncio
async def test_empty_book_is_explicitly_incomplete_and_missing() -> None:
    service = PortfolioManagerBookService(reader=_Reader([]), clock=_Clock())

    response = await service.resolve_membership(
        portfolio_manager_id="PM_EMPTY",
        request=PortfolioManagerBookMembershipRequest(
            as_of_date=date(2026, 5, 3), include_inactive=True, portfolio_types=[" "]
        ),
    )

    assert response.members == []
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "PM_BOOK_MEMBERSHIP_EMPTY"
    assert response.supportability.filters_applied == ["portfolio_manager_id", "as_of_date"]
    assert response.data_quality_status == "MISSING"
    assert response.latest_evidence_timestamp is None


@pytest.mark.asyncio
async def test_authoritative_assignment_replaces_legacy_lineage_without_changing_v1_shape() -> None:
    service = PortfolioManagerBookService(
        reader=_Reader([_record(membership_source="party_role_assignment")]), clock=_Clock()
    )

    response = await service.resolve_membership(
        portfolio_manager_id="PARTY_PM_SG_001",
        request=PortfolioManagerBookMembershipRequest(as_of_date=date(2026, 5, 3)),
    )

    assert response.members[0].membership_source == "party_role_assignment"
    assert response.members[0].role_type is PortfolioPartyRoleType.DISCRETIONARY_PORTFOLIO_MANAGER
    assert response.members[0].source_record_id == "coverage-PB_SG_GLOBAL_BAL_001-PM-001"
    assert response.lineage["source_table"] == "portfolio_party_role_assignments"
    assert response.lineage["source_field"] == "role_type"
    assert response.lineage["compatibility_policy"] == (
        "advisor_id_only_when_no_party_role_history"
    )
    assert response.latest_evidence_timestamp == datetime(2026, 5, 3, 9, 30, tzinfo=UTC)


@pytest.mark.asyncio
async def test_membership_identity_changes_when_authoritative_role_replaces_legacy() -> None:
    request = PortfolioManagerBookMembershipRequest(as_of_date=date(2026, 5, 3))
    legacy = await PortfolioManagerBookService(
        reader=_Reader([_record(membership_source="legacy_advisor_projection")]),
        clock=_Clock(),
    ).resolve_membership(portfolio_manager_id="PM_SG_DPM_001", request=request)
    authoritative = await PortfolioManagerBookService(
        reader=_Reader([_record(membership_source="party_role_assignment")]),
        clock=_Clock(),
    ).resolve_membership(portfolio_manager_id="PM_SG_DPM_001", request=request)

    assert legacy.members[0].portfolio_id == authoritative.members[0].portfolio_id
    assert legacy.snapshot_id != authoritative.snapshot_id
    assert legacy.content_hash != authoritative.content_hash
    assert legacy.source_batch_fingerprint != authoritative.source_batch_fingerprint
    assert legacy.source_digest != authoritative.source_digest


@pytest.mark.asyncio
async def test_membership_identity_changes_when_source_record_evidence_changes() -> None:
    request = PortfolioManagerBookMembershipRequest(as_of_date=date(2026, 5, 3))
    first = await PortfolioManagerBookService(
        reader=_Reader([_record(source_record_id="coverage-v1")]),
        clock=_Clock(),
    ).resolve_membership(portfolio_manager_id="PM_SG_DPM_001", request=request)
    corrected = await PortfolioManagerBookService(
        reader=_Reader([_record(source_record_id="coverage-v2")]),
        clock=_Clock(),
    ).resolve_membership(portfolio_manager_id="PM_SG_DPM_001", request=request)

    assert first.members[0].portfolio_id == corrected.members[0].portfolio_id
    assert first.snapshot_id != corrected.snapshot_id
    assert first.content_hash != corrected.content_hash
