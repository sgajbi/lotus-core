from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.reporting_repository import ReportingSnapshotRow
from src.services.query_service.app.services.liquidity_ladder_service import (
    MAX_HORIZON_DAYS,
    PortfolioLiquidityLadderService,
)

pytestmark = pytest.mark.asyncio


def _portfolio(portfolio_id: str, *, base_currency: str = "USD"):
    return SimpleNamespace(portfolio_id=portfolio_id, base_currency=base_currency)


def _instrument(
    security_id: str,
    *,
    asset_class: str = "EQUITY",
    liquidity_tier: str | None = "T1",
):
    return SimpleNamespace(
        security_id=security_id,
        asset_class=asset_class,
        liquidity_tier=liquidity_tier,
    )


def _snapshot(
    security_id: str,
    *,
    market_value: str,
    updated_at: datetime | None = None,
):
    return SimpleNamespace(
        security_id=security_id,
        market_value=Decimal(market_value),
        updated_at=updated_at,
        created_at=None,
    )


async def test_liquidity_ladder_builds_cash_buckets_and_asset_tier_exposure() -> None:
    reporting_repo = AsyncMock()
    cashflow_repo = AsyncMock()
    portfolio = _portfolio("P1")
    reporting_repo.get_portfolio_by_id.return_value = portfolio
    reporting_repo.get_latest_business_date.return_value = date(2026, 3, 27)
    reporting_repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot(
                "CASH_USD",
                market_value="100000",
                updated_at=datetime(2026, 3, 27, 9, 30, tzinfo=UTC),
            ),
            instrument=_instrument("CASH_USD", asset_class="CASH", liquidity_tier=None),
        ),
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("EQ1", market_value="400000"),
            instrument=_instrument("EQ1", liquidity_tier="T1"),
        ),
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("BOND1", market_value="250000"),
            instrument=_instrument("BOND1", liquidity_tier="T2"),
        ),
    ]
    cashflow_repo.get_portfolio_cashflow_series.return_value = [
        (date(2026, 3, 27), Decimal("-25000")),
        (date(2026, 3, 30), Decimal("5000")),
    ]
    cashflow_repo.get_projected_settlement_cashflow_series.return_value = [
        (date(2026, 3, 28), Decimal("-90000")),
        (date(2026, 4, 4), Decimal("-25000")),
    ]
    cashflow_repo.get_latest_cashflow_evidence_timestamp.return_value = datetime(
        2026, 3, 27, 10, 15, tzinfo=UTC
    )

    with (
        patch(
            "src.services.query_service.app.services.liquidity_ladder_service.ReportingRepository",
            return_value=reporting_repo,
        ),
        patch(
            "src.services.query_service.app.services.liquidity_ladder_service.CashflowRepository",
            return_value=cashflow_repo,
        ),
    ):
        service = PortfolioLiquidityLadderService(AsyncMock(spec=AsyncSession))
        response = await service.get_liquidity_ladder(portfolio_id="P1", horizon_days=8)

    assert response.product_name == "PortfolioLiquidityLadder"
    assert response.product_version == "v1"
    assert response.portfolio_currency == "USD"
    assert response.totals.opening_cash_balance_portfolio_currency == Decimal("100000")
    assert response.totals.projected_cash_available_end_portfolio_currency == Decimal("-35000")
    assert response.totals.maximum_cash_shortfall_portfolio_currency == Decimal("35000")
    assert response.totals.non_cash_market_value_portfolio_currency == Decimal("650000")
    assert response.totals.non_cash_position_count == 2
    assert [
        (tier.liquidity_tier, tier.market_value_portfolio_currency)
        for tier in response.asset_liquidity_tiers
    ] == [
        ("T1", Decimal("400000")),
        ("T2", Decimal("250000")),
    ]
    buckets = {bucket.bucket_code: bucket for bucket in response.buckets}
    assert buckets["T0"].net_cashflow_portfolio_currency == Decimal("-25000")
    assert buckets["T_PLUS_1"].projected_settlement_cashflow_portfolio_currency == Decimal("-90000")
    assert buckets["T_PLUS_2_TO_7"].booked_net_cashflow_portfolio_currency == Decimal("5000")
    assert buckets["T_PLUS_8_TO_30"].projected_settlement_cashflow_portfolio_currency == Decimal(
        "-25000"
    )
    assert response.data_quality_status == "COMPLETE"
    assert response.latest_evidence_timestamp == datetime(2026, 3, 27, 10, 15, tzinfo=UTC)
    assert response.source_batch_fingerprint == (
        "liquidity_ladder:P1:2026-03-27:2026-04-04:include_projected=true"
    )


async def test_liquidity_ladder_booked_only_omits_projected_cashflows() -> None:
    reporting_repo = AsyncMock()
    cashflow_repo = AsyncMock()
    portfolio = _portfolio("P1")
    reporting_repo.get_portfolio_by_id.return_value = portfolio
    reporting_repo.get_latest_business_date.return_value = date(2026, 3, 27)
    reporting_repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("CASH_USD", market_value="1000"),
            instrument=_instrument("CASH_USD", asset_class="CASH", liquidity_tier=None),
        )
    ]
    cashflow_repo.get_portfolio_cashflow_series.return_value = [
        (date(2026, 3, 27), Decimal("-100"))
    ]
    cashflow_repo.get_latest_cashflow_evidence_timestamp.return_value = None

    with (
        patch(
            "src.services.query_service.app.services.liquidity_ladder_service.ReportingRepository",
            return_value=reporting_repo,
        ),
        patch(
            "src.services.query_service.app.services.liquidity_ladder_service.CashflowRepository",
            return_value=cashflow_repo,
        ),
    ):
        service = PortfolioLiquidityLadderService(AsyncMock(spec=AsyncSession))
        response = await service.get_liquidity_ladder(
            portfolio_id="P1",
            horizon_days=1,
            include_projected=False,
        )

    cashflow_repo.get_projected_settlement_cashflow_series.assert_not_awaited()
    assert response.include_projected is False
    assert response.totals.projected_cash_available_end_portfolio_currency == Decimal("900")


async def test_liquidity_ladder_raises_when_portfolio_missing() -> None:
    reporting_repo = AsyncMock()
    reporting_repo.get_portfolio_by_id.return_value = None

    with patch(
        "src.services.query_service.app.services.liquidity_ladder_service.ReportingRepository",
        return_value=reporting_repo,
    ):
        service = PortfolioLiquidityLadderService(AsyncMock(spec=AsyncSession))
        with pytest.raises(ValueError, match="Portfolio with id P404 not found"):
            await service.get_liquidity_ladder(portfolio_id="P404")


async def test_liquidity_ladder_rejects_invalid_horizon_before_database_access() -> None:
    service = PortfolioLiquidityLadderService(AsyncMock(spec=AsyncSession))

    with pytest.raises(
        ValueError,
        match=f"horizon_days must be between 0 and {MAX_HORIZON_DAYS}.",
    ):
        await service.get_liquidity_ladder(
            portfolio_id="P1",
            horizon_days=MAX_HORIZON_DAYS + 1,
        )


async def test_liquidity_ladder_raises_when_business_date_missing() -> None:
    reporting_repo = AsyncMock()
    reporting_repo.get_portfolio_by_id.return_value = _portfolio("P1")
    reporting_repo.get_latest_business_date.return_value = None

    with patch(
        "src.services.query_service.app.services.liquidity_ladder_service.ReportingRepository",
        return_value=reporting_repo,
    ):
        service = PortfolioLiquidityLadderService(AsyncMock(spec=AsyncSession))
        with pytest.raises(
            ValueError,
            match="No business date is available for liquidity ladder queries.",
        ):
            await service.get_liquidity_ladder(portfolio_id="P1")


async def test_liquidity_ladder_returns_unknown_quality_for_empty_source_rows() -> None:
    reporting_repo = AsyncMock()
    cashflow_repo = AsyncMock()
    portfolio = _portfolio("P1")
    reporting_repo.get_portfolio_by_id.return_value = portfolio
    reporting_repo.get_latest_business_date.return_value = date(2026, 3, 27)
    reporting_repo.list_latest_snapshot_rows.return_value = []
    cashflow_repo.get_portfolio_cashflow_series.return_value = []
    cashflow_repo.get_projected_settlement_cashflow_series.return_value = []
    cashflow_repo.get_latest_cashflow_evidence_timestamp.return_value = None

    with (
        patch(
            "src.services.query_service.app.services.liquidity_ladder_service.ReportingRepository",
            return_value=reporting_repo,
        ),
        patch(
            "src.services.query_service.app.services.liquidity_ladder_service.CashflowRepository",
            return_value=cashflow_repo,
        ),
    ):
        service = PortfolioLiquidityLadderService(AsyncMock(spec=AsyncSession))
        response = await service.get_liquidity_ladder(portfolio_id="P1", horizon_days=0)

    assert response.data_quality_status == "UNKNOWN"
    assert response.latest_evidence_timestamp is None
    assert response.asset_liquidity_tiers == []
    assert [bucket.bucket_code for bucket in response.buckets] == ["T0"]
    assert response.totals.opening_cash_balance_portfolio_currency == Decimal("0")


async def test_liquidity_ladder_classifies_unavailable_tier_and_missing_market_value() -> None:
    reporting_repo = AsyncMock()
    cashflow_repo = AsyncMock()
    portfolio = _portfolio("P1")
    reporting_repo.get_portfolio_by_id.return_value = portfolio
    reporting_repo.get_latest_business_date.return_value = date(2026, 3, 27)
    reporting_repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=SimpleNamespace(
                security_id="ALT1",
                market_value=None,
                updated_at=None,
                created_at=datetime(2026, 3, 27, 8, 0, tzinfo=UTC),
            ),
            instrument=_instrument("ALT1", liquidity_tier=None),
        )
    ]
    cashflow_repo.get_portfolio_cashflow_series.return_value = []
    cashflow_repo.get_projected_settlement_cashflow_series.return_value = []
    cashflow_repo.get_latest_cashflow_evidence_timestamp.return_value = None

    with (
        patch(
            "src.services.query_service.app.services.liquidity_ladder_service.ReportingRepository",
            return_value=reporting_repo,
        ),
        patch(
            "src.services.query_service.app.services.liquidity_ladder_service.CashflowRepository",
            return_value=cashflow_repo,
        ),
    ):
        service = PortfolioLiquidityLadderService(AsyncMock(spec=AsyncSession))
        response = await service.get_liquidity_ladder(portfolio_id="P1", horizon_days=0)

    assert response.asset_liquidity_tiers[0].liquidity_tier == "UNCLASSIFIED"
    assert response.asset_liquidity_tiers[0].market_value_portfolio_currency == Decimal("0")
    assert response.latest_evidence_timestamp == datetime(2026, 3, 27, 8, 0, tzinfo=UTC)
