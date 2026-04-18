from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.reporting_repository import ReportingSnapshotRow
from src.services.query_service.app.services.cash_balance_service import CashBalanceService

pytestmark = pytest.mark.asyncio


def _portfolio(portfolio_id: str, *, base_currency: str = "USD"):
    return SimpleNamespace(portfolio_id=portfolio_id, base_currency=base_currency)


def _instrument(
    security_id: str,
    *,
    name: str = "Instrument",
    currency: str = "USD",
    asset_class: str | None = "EQUITY",
):
    return SimpleNamespace(
        security_id=security_id,
        name=name,
        currency=currency,
        asset_class=asset_class,
    )


def _snapshot(
    security_id: str,
    *,
    market_value: str,
    market_value_local: str | None = None,
    updated_at: datetime | None = None,
):
    return SimpleNamespace(
        security_id=security_id,
        market_value=Decimal(market_value),
        market_value_local=Decimal(market_value_local or market_value),
        updated_at=updated_at,
        created_at=None,
    )


async def test_get_cash_balances_returns_holdings_as_of_balances_and_metadata() -> None:
    repo = AsyncMock()
    portfolio = _portfolio("P1", base_currency="USD")
    repo.get_portfolio_by_id.return_value = portfolio
    repo.get_latest_business_date.return_value = date(2026, 3, 27)
    repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot(
                "CASH_USD",
                market_value="250",
                updated_at=datetime(2026, 3, 27, 11, 15, tzinfo=UTC),
            ),
            instrument=_instrument(
                "CASH_USD",
                name="USD Cash Account",
                currency="USD",
                asset_class="CASH",
            ),
        ),
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("SEC1", market_value="100"),
            instrument=_instrument("SEC1"),
        ),
    ]
    repo.get_latest_cash_account_ids.return_value = {"CASH_USD": "CASH-ACC-USD-001"}
    repo.get_latest_fx_rate.return_value = Decimal("1.2")

    with patch(
        "src.services.query_service.app.services.cash_balance_service.ReportingRepository",
        return_value=repo,
    ):
        service = CashBalanceService(AsyncMock(spec=AsyncSession))
        response = await service.get_cash_balances(
            portfolio_id="P1",
            reporting_currency="SGD",
        )

    assert response.portfolio_id == "P1"
    assert response.product_name == "HoldingsAsOf"
    assert response.product_version == "v1"
    assert response.as_of_date == date(2026, 3, 27)
    assert response.totals.cash_account_count == 1
    assert response.totals.total_balance_portfolio_currency == Decimal("250")
    assert response.totals.total_balance_reporting_currency == Decimal("300.0")
    assert response.cash_accounts[0].cash_account_id == "CASH-ACC-USD-001"
    assert response.data_quality_status == "COMPLETE"
    assert response.latest_evidence_timestamp == datetime(2026, 3, 27, 11, 15, tzinfo=UTC)


async def test_get_cash_balances_prefers_master_rows_and_preserves_zero_balance_accounts() -> None:
    repo = AsyncMock()
    portfolio = _portfolio("P1", base_currency="USD")
    repo.get_portfolio_by_id.return_value = portfolio
    repo.get_latest_business_date.return_value = date(2026, 3, 27)
    repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("CASH_USD", market_value="250"),
            instrument=_instrument(
                "CASH_USD",
                name="USD Cash Account",
                currency="USD",
                asset_class="CASH",
            ),
        )
    ]
    repo.list_cash_account_masters.return_value = [
        SimpleNamespace(
            cash_account_id="CASH-ACC-USD-001",
            security_id="CASH_USD",
            display_name="USD Operating Cash",
            account_currency="USD",
        ),
        SimpleNamespace(
            cash_account_id="CASH-ACC-SGD-001",
            security_id="CASH_SGD",
            display_name="SGD Reserve Cash",
            account_currency="SGD",
        ),
    ]
    repo.get_latest_cash_account_ids.return_value = {"CASH_USD": "LEGACY-MAP"}

    with patch(
        "src.services.query_service.app.services.cash_balance_service.ReportingRepository",
        return_value=repo,
    ):
        service = CashBalanceService(AsyncMock(spec=AsyncSession))
        response = await service.get_cash_balances(portfolio_id="P1")

    assert [record.cash_account_id for record in response.cash_accounts] == [
        "CASH-ACC-SGD-001",
        "CASH-ACC-USD-001",
    ]
    assert response.cash_accounts[0].balance_portfolio_currency == Decimal("0")
    assert response.cash_accounts[1].balance_portfolio_currency == Decimal("250")
    assert response.totals.cash_account_count == 2
    assert response.data_quality_status == "COMPLETE"


async def test_get_cash_balances_raises_when_portfolio_missing() -> None:
    repo = AsyncMock()
    repo.get_portfolio_by_id.return_value = None

    with patch(
        "src.services.query_service.app.services.cash_balance_service.ReportingRepository",
        return_value=repo,
    ):
        service = CashBalanceService(AsyncMock(spec=AsyncSession))
        with pytest.raises(ValueError, match="Portfolio with id P404 not found"):
            await service.get_cash_balances(portfolio_id="P404")
