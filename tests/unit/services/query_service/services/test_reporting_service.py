from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.dtos.reporting_dto import (
    AssetAllocationQueryRequest,
    AssetsUnderManagementQueryRequest,
    CashBalancesQueryRequest,
    ReportingScope,
)
from src.services.query_service.app.repositories.reporting_repository import ReportingSnapshotRow
from src.services.query_service.app.services.reporting_service import ReportingService

pytestmark = pytest.mark.asyncio


def _portfolio(
    portfolio_id: str,
    *,
    base_currency: str = "USD",
    booking_center_code: str = "SGPB",
    client_id: str = "CIF-1",
):
    return SimpleNamespace(
        portfolio_id=portfolio_id,
        base_currency=base_currency,
        booking_center_code=booking_center_code,
        client_id=client_id,
    )


def _instrument(
    security_id: str,
    *,
    name: str = "Instrument",
    currency: str = "USD",
    asset_class: str | None = "EQUITY",
    sector: str | None = "TECH",
    country_of_risk: str | None = "US",
    product_type: str | None = "EQUITY",
    rating: str | None = None,
    issuer_id: str | None = None,
    issuer_name: str | None = None,
    ultimate_parent_issuer_id: str | None = None,
    ultimate_parent_issuer_name: str | None = None,
):
    return SimpleNamespace(
        security_id=security_id,
        name=name,
        currency=currency,
        asset_class=asset_class,
        sector=sector,
        country_of_risk=country_of_risk,
        product_type=product_type,
        rating=rating,
        issuer_id=issuer_id,
        issuer_name=issuer_name,
        ultimate_parent_issuer_id=ultimate_parent_issuer_id,
        ultimate_parent_issuer_name=ultimate_parent_issuer_name,
    )


def _snapshot(
    security_id: str,
    *,
    market_value: str,
    market_value_local: str | None = None,
):
    return SimpleNamespace(
        security_id=security_id,
        market_value=Decimal(market_value),
        market_value_local=Decimal(market_value_local or market_value),
    )


async def test_get_assets_under_management_defaults_to_portfolio_currency_for_single_scope(
) -> None:
    repo = AsyncMock()
    portfolio = _portfolio("P1", base_currency="USD")
    repo.get_latest_business_date.return_value = date(2026, 3, 27)
    repo.list_portfolios.return_value = [portfolio]
    repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("SEC1", market_value="100"),
            instrument=_instrument("SEC1"),
        ),
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("SEC2", market_value="50"),
            instrument=_instrument("SEC2", sector="HEALTHCARE"),
        ),
    ]

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        response = await service.get_assets_under_management(
            AssetsUnderManagementQueryRequest(
                scope=ReportingScope(portfolio_id="P1"),
            )
        )

    assert response.reporting_currency == "USD"
    assert response.totals.aum_reporting_currency == Decimal("150")
    assert response.totals.position_count == 2
    assert response.portfolios[0].aum_portfolio_currency == Decimal("150")


async def test_get_asset_allocation_groups_requested_dimensions_with_fx_conversion() -> None:
    repo = AsyncMock()
    portfolio = _portfolio("P1", base_currency="USD")
    repo.get_latest_business_date.return_value = date(2026, 3, 27)
    repo.list_portfolios.return_value = [portfolio]
    repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("SEC1", market_value="100"),
            instrument=_instrument("SEC1", asset_class="EQUITY", sector="TECH", currency="USD"),
        ),
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("SEC2", market_value="40"),
            instrument=_instrument("SEC2", asset_class="BOND", sector="RATES", currency="EUR"),
        ),
    ]
    repo.get_latest_fx_rate.side_effect = lambda **kwargs: Decimal("1.5")

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        response = await service.get_asset_allocation(
            AssetAllocationQueryRequest(
                scope=ReportingScope(portfolio_ids=["P1"]),
                reporting_currency="SGD",
                dimensions=["asset_class", "currency"],
            )
        )

    assert response.reporting_currency == "SGD"
    assert response.total_market_value_reporting_currency == Decimal("210")
    asset_class_view = next(
        view for view in response.views if view.dimension == "asset_class"
    )
    equity_bucket = next(
        bucket
        for bucket in asset_class_view.buckets
        if bucket.dimension_value == "EQUITY"
    )
    bond_bucket = next(
        bucket for bucket in asset_class_view.buckets if bucket.dimension_value == "BOND"
    )
    assert equity_bucket.market_value_reporting_currency == Decimal("150")
    assert bond_bucket.market_value_reporting_currency == Decimal("60")


async def test_get_cash_balances_returns_cash_accounts_and_totals() -> None:
    repo = AsyncMock()
    portfolio = _portfolio("P1", base_currency="USD")
    repo.get_portfolio_by_id.return_value = portfolio
    repo.get_latest_business_date.return_value = date(2026, 3, 27)
    repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("CASH_USD", market_value="250", market_value_local="250"),
            instrument=_instrument(
                "CASH_USD",
                name="USD Cash Account",
                currency="USD",
                asset_class="CASH",
                sector="CASH",
                product_type="CASH",
            ),
        ),
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("SEC1", market_value="100"),
            instrument=_instrument("SEC1", asset_class="EQUITY"),
        ),
    ]
    repo.get_latest_cash_account_ids.return_value = {"CASH_USD": "CASH-ACC-USD-001"}
    repo.get_latest_fx_rate.side_effect = lambda **kwargs: Decimal("1.2")

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        response = await service.get_cash_balances(
            CashBalancesQueryRequest(portfolio_id="P1", reporting_currency="SGD")
        )

    assert response.portfolio_id == "P1"
    assert response.totals.cash_account_count == 1
    assert response.totals.total_balance_portfolio_currency == Decimal("250")
    assert response.totals.total_balance_reporting_currency == Decimal("300.0")
    assert response.cash_accounts[0].cash_account_id == "CASH-ACC-USD-001"


async def test_get_cash_balances_raises_when_portfolio_missing() -> None:
    repo = AsyncMock()
    repo.get_portfolio_by_id.return_value = None

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        with pytest.raises(ValueError, match="Portfolio with id P404 not found"):
            await service.get_cash_balances(CashBalancesQueryRequest(portfolio_id="P404"))
