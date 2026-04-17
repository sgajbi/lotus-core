from datetime import date

import pytest
from pydantic import ValidationError

from src.services.query_service.app.dtos.reporting_dto import (
    AssetAllocationQueryRequest,
    AssetsUnderManagementQueryRequest,
    PortfolioSummaryQueryRequest,
    ReportingScope,
    ReportingWindow,
)


def test_reporting_scope_requires_exactly_one_selector() -> None:
    with pytest.raises(ValidationError, match="Exactly one scope selector is required"):
        ReportingScope(portfolio_id="P1", booking_center_code="SGPB")


def test_aum_request_requires_reporting_currency_for_multi_portfolio_scope() -> None:
    with pytest.raises(ValidationError, match="reporting_currency is required"):
        AssetsUnderManagementQueryRequest(
            scope=ReportingScope(portfolio_ids=["P1", "P2"]),
            as_of_date=date(2026, 3, 27),
        )


def test_asset_allocation_request_accepts_single_portfolio_without_reporting_currency() -> None:
    request = AssetAllocationQueryRequest(
        scope=ReportingScope(portfolio_id="P1"),
        as_of_date=date(2026, 3, 27),
        dimensions=["asset_class", "sector"],
    )

    assert request.scope.scope_type == "portfolio"
    assert request.reporting_currency is None


def test_reporting_window_rejects_inverted_dates() -> None:
    with pytest.raises(ValidationError, match="start_date cannot be after end_date"):
        ReportingWindow(start_date=date(2026, 3, 27), end_date=date(2026, 1, 1))

def test_asset_allocation_request_supports_region_and_lookthrough_mode() -> None:
    request = AssetAllocationQueryRequest(
        scope=ReportingScope(portfolio_id="P1"),
        dimensions=["region", "asset_class"],
        look_through_mode="prefer_look_through",
    )

    assert request.dimensions == ["region", "asset_class"]
    assert request.look_through_mode == "prefer_look_through"


def test_portfolio_summary_request_is_single_portfolio_contract() -> None:
    request = PortfolioSummaryQueryRequest(portfolio_id="P1", reporting_currency="USD")

    assert request.portfolio_id == "P1"
    assert request.reporting_currency == "USD"


