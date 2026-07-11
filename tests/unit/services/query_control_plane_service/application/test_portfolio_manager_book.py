"""Behavior tests for QCP-owned portfolio-manager book membership."""

from datetime import UTC, date, datetime

import pytest

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


def _record() -> PortfolioManagerBookRecord:
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
