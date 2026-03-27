from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.dtos.reporting_dto import (
    ActivitySummaryQueryRequest,
    AssetAllocationQueryRequest,
    AssetsUnderManagementQueryRequest,
    CashBalancesQueryRequest,
    IncomeSummaryQueryRequest,
    ReportingScope,
    ReportingWindow,
)
from src.services.query_service.app.repositories.reporting_repository import (
    ActivitySummaryAggregateRow,
    IncomeSummaryAggregateRow,
    ReportingSnapshotRow,
)
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


async def test_get_assets_under_management_defaults_to_portfolio_currency_for_single_scope() -> (
    None
):
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
    asset_class_view = next(view for view in response.views if view.dimension == "asset_class")
    equity_bucket = next(
        bucket for bucket in asset_class_view.buckets if bucket.dimension_value == "EQUITY"
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


async def test_get_income_summary_returns_requested_window_and_ytd_amounts() -> None:
    repo = AsyncMock()
    portfolio = _portfolio("P1", base_currency="USD")
    repo.list_portfolios.return_value = [portfolio]
    repo.list_income_summary_rows.return_value = [
        IncomeSummaryAggregateRow(
            portfolio_id="P1",
            booking_center_code="SGPB",
            client_id="CIF-1",
            portfolio_currency="USD",
            source_currency="USD",
            income_type="DIVIDEND",
            requested_transaction_count=1,
            ytd_transaction_count=2,
            requested_gross_amount=Decimal("50"),
            ytd_gross_amount=Decimal("80"),
            requested_withholding_tax=Decimal("0"),
            ytd_withholding_tax=Decimal("0"),
            requested_other_deductions=Decimal("0"),
            ytd_other_deductions=Decimal("0"),
            requested_net_amount=Decimal("50"),
            ytd_net_amount=Decimal("80"),
        ),
        IncomeSummaryAggregateRow(
            portfolio_id="P1",
            booking_center_code="SGPB",
            client_id="CIF-1",
            portfolio_currency="USD",
            source_currency="USD",
            income_type="INTEREST",
            requested_transaction_count=1,
            ytd_transaction_count=1,
            requested_gross_amount=Decimal("30"),
            ytd_gross_amount=Decimal("30"),
            requested_withholding_tax=Decimal("3"),
            ytd_withholding_tax=Decimal("3"),
            requested_other_deductions=Decimal("1"),
            ytd_other_deductions=Decimal("1"),
            requested_net_amount=Decimal("26"),
            ytd_net_amount=Decimal("26"),
        ),
    ]

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        response = await service.get_income_summary(
            IncomeSummaryQueryRequest(
                scope=ReportingScope(portfolio_id="P1"),
                window=ReportingWindow(start_date=date(2026, 3, 1), end_date=date(2026, 3, 27)),
            )
        )

    assert response.reporting_currency == "USD"
    assert response.totals.requested_window.gross_amount_portfolio_currency == Decimal("80")
    assert response.totals.requested_window.net_amount_reporting_currency == Decimal("76")
    assert response.totals.year_to_date.gross_amount_reporting_currency == Decimal("110")
    interest_bucket = next(
        bucket for bucket in response.portfolios[0].income_types if bucket.income_type == "INTEREST"
    )
    assert interest_bucket.requested_window.withholding_tax_reporting_currency == Decimal("3")


async def test_get_activity_summary_returns_flow_buckets_with_reporting_conversion() -> None:
    repo = AsyncMock()
    portfolio = _portfolio("P1", base_currency="USD")
    repo.list_portfolios.return_value = [portfolio]
    repo.list_activity_summary_rows.return_value = [
        ActivitySummaryAggregateRow(
            portfolio_id="P1",
            booking_center_code="SGPB",
            client_id="CIF-1",
            portfolio_currency="USD",
            source_currency="USD",
            bucket="INFLOWS",
            requested_transaction_count=1,
            ytd_transaction_count=2,
            requested_amount=Decimal("1000"),
            ytd_amount=Decimal("1500"),
        ),
        ActivitySummaryAggregateRow(
            portfolio_id="P1",
            booking_center_code="SGPB",
            client_id="CIF-1",
            portfolio_currency="USD",
            source_currency="USD",
            bucket="FEES",
            requested_transaction_count=1,
            ytd_transaction_count=1,
            requested_amount=Decimal("25"),
            ytd_amount=Decimal("25"),
        ),
    ]
    repo.get_latest_fx_rate.side_effect = lambda **kwargs: Decimal("1.2")

    with patch(
        "src.services.query_service.app.services.reporting_service.ReportingRepository",
        return_value=repo,
    ):
        service = ReportingService(AsyncMock(spec=AsyncSession))
        response = await service.get_activity_summary(
            ActivitySummaryQueryRequest(
                scope=ReportingScope(portfolio_ids=["P1"]),
                reporting_currency="SGD",
                window=ReportingWindow(start_date=date(2026, 3, 1), end_date=date(2026, 3, 27)),
            )
        )

    inflows_bucket = next(
        bucket for bucket in response.totals.buckets if bucket.bucket == "INFLOWS"
    )
    fees_bucket = next(bucket for bucket in response.totals.buckets if bucket.bucket == "FEES")
    taxes_bucket = next(bucket for bucket in response.totals.buckets if bucket.bucket == "TAXES")

    assert inflows_bucket.requested_window.amount_reporting_currency == Decimal("1200.0")
    assert inflows_bucket.year_to_date.amount_reporting_currency == Decimal("1800.0")
    assert fees_bucket.requested_window.amount_reporting_currency == Decimal("30.0")
    assert taxes_bucket.requested_window.amount_reporting_currency == Decimal("0")
