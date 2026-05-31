from datetime import UTC, date, datetime
from types import SimpleNamespace

from src.services.query_service.app.dtos.reference_integration_dto import (
    PortfolioManagerBookMembershipRequest,
)
from src.services.query_service.app.services.portfolio_manager_book_membership import (
    build_portfolio_manager_book_membership_response,
    portfolio_manager_book_membership_portfolio_types,
)


def _membership_request(
    *,
    include_inactive: bool = False,
    portfolio_types: list[str] | None = None,
) -> PortfolioManagerBookMembershipRequest:
    return PortfolioManagerBookMembershipRequest(
        as_of_date=date(2026, 5, 3),
        booking_center_code="Singapore",
        portfolio_types=portfolio_types if portfolio_types is not None else ["DISCRETIONARY"],
        include_inactive=include_inactive,
    )


def _portfolio_row(portfolio_id: str = "PB_SG_GLOBAL_BAL_001") -> SimpleNamespace:
    return SimpleNamespace(
        portfolio_id=portfolio_id,
        client_id="CIF_SG_GLOBAL_BAL_001",
        booking_center_code="Singapore",
        portfolio_type="DISCRETIONARY",
        status="ACTIVE",
        open_date=date(2025, 3, 31),
        close_date=None,
        base_currency="USD",
        created_at=datetime(2026, 5, 3, 1, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 3, 1, 5, tzinfo=UTC),
    )


def test_portfolio_manager_book_membership_portfolio_types_normalizes_scope() -> None:
    request = _membership_request(portfolio_types=[" discretionary ", "", "advisory"])

    assert portfolio_manager_book_membership_portfolio_types(request) == [
        "DISCRETIONARY",
        "ADVISORY",
    ]


def test_build_portfolio_manager_book_membership_response_marks_ready() -> None:
    request = _membership_request()

    response = build_portfolio_manager_book_membership_response(
        portfolio_manager_id="PM_SG_DPM_001",
        request=request,
        portfolio_types=portfolio_manager_book_membership_portfolio_types(request),
        rows=[_portfolio_row()],
    )

    assert response.product_name == "PortfolioManagerBookMembership"
    assert response.portfolio_manager_id == "PM_SG_DPM_001"
    assert response.members[0].portfolio_id == "PB_SG_GLOBAL_BAL_001"
    assert response.members[0].source_record_id == "portfolio:PB_SG_GLOBAL_BAL_001"
    assert response.supportability.state == "READY"
    assert response.supportability.reason == "PM_BOOK_MEMBERSHIP_READY"
    assert response.supportability.returned_portfolio_count == 1
    assert response.supportability.filters_applied == [
        "portfolio_manager_id",
        "as_of_date",
        "booking_center_code",
        "portfolio_types",
        "active_lifecycle_window",
        "active_status",
    ]
    assert response.data_quality_status == "ACCEPTED"
    assert response.latest_evidence_timestamp == datetime(2026, 5, 3, 1, 5, tzinfo=UTC)
    assert response.snapshot_id is not None
    assert response.snapshot_id.startswith("pm_book_membership:")
    assert response.lineage == {
        "source_system": "lotus-core",
        "source_table": "portfolios",
        "source_field": "advisor_id",
        "contract_version": "rfc_041_pm_book_membership_v1",
    }


def test_build_portfolio_manager_book_membership_response_marks_empty_book_missing() -> None:
    request = _membership_request(include_inactive=True, portfolio_types=[" "])

    response = build_portfolio_manager_book_membership_response(
        portfolio_manager_id="PM_EMPTY",
        request=request,
        portfolio_types=portfolio_manager_book_membership_portfolio_types(request),
        rows=[],
    )

    assert response.members == []
    assert response.supportability.state == "INCOMPLETE"
    assert response.supportability.reason == "PM_BOOK_MEMBERSHIP_EMPTY"
    assert response.supportability.returned_portfolio_count == 0
    assert response.supportability.filters_applied == [
        "portfolio_manager_id",
        "as_of_date",
        "booking_center_code",
    ]
    assert response.data_quality_status == "MISSING"
    assert response.latest_evidence_timestamp is None
