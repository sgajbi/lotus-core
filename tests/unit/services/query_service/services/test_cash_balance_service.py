from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.reporting_repository import ReportingSnapshotRow
from src.services.query_service.app.services.cash_balance_service import (
    CashBalanceResolver,
    CashBalanceService,
)

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
    portfolio = _portfolio("P1", base_currency=" usd ")
    repo.get_portfolio_by_id.return_value = portfolio
    repo.get_latest_business_date.return_value = date(2026, 3, 27)
    repo.list_cash_account_masters.return_value = []
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
                currency=" usd ",
                asset_class=" cash ",
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
            reporting_currency=" sgd ",
        )

    assert response.portfolio_id == "P1"
    assert response.portfolio_currency == "USD"
    assert response.reporting_currency == "SGD"
    assert response.product_name == "HoldingsAsOf"
    assert response.product_version == "v1"
    assert response.as_of_date == date(2026, 3, 27)
    assert response.totals.cash_account_count == 1
    assert response.totals.total_balance_portfolio_currency == Decimal("250")
    assert response.totals.total_balance_reporting_currency == Decimal("300.0")
    assert response.cash_accounts[0].cash_account_id == "CASH-ACC-USD-001"
    assert response.cash_accounts[0].account_currency == "USD"
    assert response.data_quality_status == "COMPLETE"
    assert response.latest_evidence_timestamp == datetime(2026, 3, 27, 11, 15, tzinfo=UTC)
    repo.list_latest_snapshot_rows.assert_awaited_once_with(
        portfolio_ids=["P1"],
        as_of_date=date(2026, 3, 27),
        instrument_asset_class="CASH",
    )
    repo.get_latest_fx_rate.assert_awaited_once_with(
        from_currency="USD",
        to_currency="SGD",
        as_of_date=date(2026, 3, 27),
    )
    repo.get_latest_cash_account_ids.assert_awaited_once_with(
        portfolio_id="P1",
        cash_security_ids=["CASH_USD"],
        as_of_date=date(2026, 3, 27),
    )


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
    repo.get_latest_cash_account_ids.assert_not_awaited()


async def test_get_cash_balances_queries_fallback_account_ids_only_for_unmatched_cash() -> None:
    repo = AsyncMock()
    portfolio = _portfolio("P1", base_currency="USD")
    repo.get_portfolio_by_id.return_value = portfolio
    repo.get_latest_business_date.return_value = date(2026, 3, 27)
    repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("CASH_USD", market_value="250"),
            instrument=_instrument("CASH_USD", asset_class="CASH"),
        ),
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("CASH_EUR", market_value="125"),
            instrument=_instrument("CASH_EUR", currency="EUR", asset_class="CASH"),
        ),
    ]
    repo.list_cash_account_masters.return_value = [
        SimpleNamespace(
            cash_account_id="CASH-ACC-USD-001",
            security_id="CASH_USD",
            display_name="USD Operating Cash",
            account_currency="USD",
        )
    ]
    repo.get_latest_cash_account_ids.return_value = {"CASH_EUR": "CASH-ACC-EUR-LEGACY"}

    with patch(
        "src.services.query_service.app.services.cash_balance_service.ReportingRepository",
        return_value=repo,
    ):
        service = CashBalanceService(AsyncMock(spec=AsyncSession))
        response = await service.get_cash_balances(portfolio_id="P1")

    assert [record.cash_account_id for record in response.cash_accounts] == [
        "CASH-ACC-EUR-LEGACY",
        "CASH-ACC-USD-001",
    ]
    repo.get_latest_cash_account_ids.assert_awaited_once_with(
        portfolio_id="P1",
        cash_security_ids=["CASH_EUR"],
        as_of_date=date(2026, 3, 27),
    )


async def test_cash_balance_records_build_account_conversions_sequentially() -> None:
    repo = AsyncMock()
    portfolio = _portfolio("P1", base_currency="USD")
    repo.list_cash_account_masters.return_value = [
        SimpleNamespace(
            cash_account_id="CASH-ACC-USD-001",
            security_id="CASH_USD",
            display_name="USD Operating Cash",
            account_currency="USD",
        )
    ]
    repo.get_latest_cash_account_ids.return_value = {"CASH_EUR": "CASH-ACC-EUR-LEGACY"}
    cash_rows = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("CASH_USD", market_value="250"),
            instrument=_instrument("CASH_USD", currency="USD", asset_class="CASH"),
        ),
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("CASH_EUR", market_value="125"),
            instrument=_instrument("CASH_EUR", currency="EUR", asset_class="CASH"),
        ),
    ]
    call_order: list[Decimal] = []

    async def convert_amount(
        *,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Decimal:
        call_order.append(amount)
        assert from_currency == "USD"
        assert to_currency == "SGD"
        assert as_of_date == date(2026, 3, 27)
        return amount * Decimal("1.2")

    resolver = CashBalanceResolver(repo=repo, convert_amount=convert_amount)

    records = await resolver.build_cash_account_balance_records(
        portfolio=portfolio,
        cash_rows=cash_rows,
        resolved_as_of_date=date(2026, 3, 27),
        reporting_currency="SGD",
    )

    assert [record.cash_account_id for record in records] == [
        "CASH-ACC-EUR-LEGACY",
        "CASH-ACC-USD-001",
    ]
    assert [record.balance_reporting_currency for record in records] == [
        Decimal("150.0"),
        Decimal("300.0"),
    ]
    assert call_order == [Decimal("250"), Decimal("125")]


async def test_get_cash_balances_normalizes_cash_security_ids_for_master_join() -> None:
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
            security_id=" CASH_USD ",
            display_name="USD Operating Cash",
            account_currency=" usd ",
        )
    ]
    repo.get_latest_cash_account_ids.return_value = {}

    with patch(
        "src.services.query_service.app.services.cash_balance_service.ReportingRepository",
        return_value=repo,
    ):
        service = CashBalanceService(AsyncMock(spec=AsyncSession))
        response = await service.get_cash_balances(portfolio_id="P1")

    assert response.cash_accounts[0].cash_account_id == "CASH-ACC-USD-001"
    assert response.cash_accounts[0].security_id == "CASH_USD"
    assert response.cash_accounts[0].account_currency == "USD"
    assert response.cash_accounts[0].balance_portfolio_currency == Decimal("250")
    assert response.totals.total_balance_portfolio_currency == Decimal("250")
    repo.get_latest_cash_account_ids.assert_not_awaited()


async def test_get_cash_balances_reads_portfolio_and_default_date_sequentially() -> None:
    repo = AsyncMock()
    call_order: list[str] = []
    repo.list_latest_snapshot_rows.return_value = []
    repo.list_cash_account_masters.return_value = []

    async def get_portfolio_by_id(portfolio_id: str):
        call_order.append("portfolio")
        assert portfolio_id == "P1"
        return _portfolio("P1", base_currency="USD")

    async def get_latest_business_date() -> date:
        call_order.append("date")
        return date(2026, 3, 27)

    repo.get_portfolio_by_id.side_effect = get_portfolio_by_id
    repo.get_latest_business_date.side_effect = get_latest_business_date

    with patch(
        "src.services.query_service.app.services.cash_balance_service.ReportingRepository",
        return_value=repo,
    ):
        service = CashBalanceService(AsyncMock(spec=AsyncSession))
        response = await service.get_cash_balances(portfolio_id="P1")

    assert response.resolved_as_of_date == date(2026, 3, 27)
    assert call_order == ["portfolio", "date"]


async def test_get_cash_balances_explicit_date_skips_default_date_lookup() -> None:
    repo = AsyncMock()
    portfolio = _portfolio("P1", base_currency="USD")
    repo.get_portfolio_by_id.return_value = portfolio
    repo.list_latest_snapshot_rows.return_value = []
    repo.list_cash_account_masters.return_value = []

    with patch(
        "src.services.query_service.app.services.cash_balance_service.ReportingRepository",
        return_value=repo,
    ):
        service = CashBalanceService(AsyncMock(spec=AsyncSession))
        response = await service.get_cash_balances(
            portfolio_id="P1",
            as_of_date=date(2026, 3, 26),
        )

    assert response.resolved_as_of_date == date(2026, 3, 26)
    repo.get_latest_business_date.assert_not_awaited()


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


async def test_cash_balance_service_normalizes_fx_cache_and_identity_checks() -> None:
    repo = AsyncMock()
    repo.get_latest_fx_rate.return_value = Decimal("1.35")

    with patch(
        "src.services.query_service.app.services.cash_balance_service.ReportingRepository",
        return_value=repo,
    ):
        service = CashBalanceService(AsyncMock(spec=AsyncSession))

        same_currency = await service._convert_amount(
            amount=Decimal("10"),
            from_currency=" sgd ",
            to_currency="SGD",
            as_of_date=date(2026, 3, 27),
        )
        first_rate = await service._get_fx_rate(" usd ", " sgd ", date(2026, 3, 27))
        second_rate = await service._get_fx_rate("USD", "SGD", date(2026, 3, 27))

    assert same_currency == Decimal("10")
    assert first_rate == Decimal("1.35")
    assert second_rate == Decimal("1.35")
    repo.get_latest_fx_rate.assert_awaited_once_with(
        from_currency="USD",
        to_currency="SGD",
        as_of_date=date(2026, 3, 27),
    )
