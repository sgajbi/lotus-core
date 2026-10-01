from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.cashflow_repository import CashflowSeriesEvidence
from src.services.query_service.app.repositories.reporting_repository import ReportingSnapshotRow
from src.services.query_service.app.services.liquidity_ladder_service import (
    MAX_HORIZON_DAYS,
    PortfolioLiquidityLadderService,
)
from tests.test_support.tenant import TEST_TENANT_CONTEXT

pytestmark = pytest.mark.asyncio


def _portfolio(portfolio_id: str, *, base_currency: str = "USD"):
    return SimpleNamespace(portfolio_id=portfolio_id, base_currency=base_currency)


def _instrument(
    security_id: str,
    *,
    asset_class: str | None = "EQUITY",
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
    market_value: str | None,
    valuation_status: str | None = "VALUED_CURRENT",
    snapshot_date: date = date(2026, 3, 27),
    updated_at: datetime | None = None,
):
    return SimpleNamespace(
        security_id=security_id,
        market_value=Decimal(market_value) if market_value is not None else None,
        valuation_status=valuation_status,
        date=snapshot_date,
        updated_at=updated_at,
        created_at=None,
    )


async def test_liquidity_ladder_builds_cash_buckets_and_asset_tier_exposure() -> None:
    reporting_repo = AsyncMock()
    cashflow_repo = AsyncMock()
    portfolio = _portfolio("P1", base_currency=" usd ")
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
            instrument=_instrument("CASH_USD", asset_class=" cash ", liquidity_tier=None),
        ),
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("EQ1", market_value="400000"),
            instrument=_instrument("EQ1", liquidity_tier=" t1 "),
        ),
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("BOND1", market_value="250000"),
            instrument=_instrument("BOND1", liquidity_tier=" t2 "),
        ),
    ]
    cashflow_repo.get_portfolio_cashflow_series_with_evidence.return_value = CashflowSeriesEvidence(
        rows=[
            (date(2026, 3, 27), Decimal("-25000")),
            (date(2026, 3, 30), Decimal("5000")),
        ],
        latest_evidence_timestamp=datetime(2026, 3, 27, 9, 45, tzinfo=UTC),
    )
    cashflow_repo.get_projected_settlement_cashflow_series_with_evidence.return_value = (
        CashflowSeriesEvidence(
            rows=[
                (date(2026, 3, 28), Decimal("-90000")),
                (date(2026, 4, 4), Decimal("-25000")),
            ],
            latest_evidence_timestamp=datetime(2026, 3, 27, 10, 15, tzinfo=UTC),
        )
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
        response = await service.get_liquidity_ladder(
            portfolio_id="P1", horizon_days=8, tenant_context=TEST_TENANT_CONTEXT
        )

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
    assert response.source_batch_fingerprint is None


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
    cashflow_repo.get_portfolio_cashflow_series_with_evidence.return_value = CashflowSeriesEvidence(
        rows=[(date(2026, 3, 27), Decimal("-100"))],
        latest_evidence_timestamp=None,
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
        response = await service.get_liquidity_ladder(
            portfolio_id="P1",
            horizon_days=1,
            include_projected=False,
            tenant_context=TEST_TENANT_CONTEXT,
        )

    cashflow_repo.get_projected_settlement_cashflow_series_with_evidence.assert_not_awaited()
    assert response.include_projected is False
    assert response.totals.projected_cash_available_end_portfolio_currency == Decimal("900")


async def test_liquidity_ladder_runs_booked_and_projected_reads_sequentially() -> None:
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
    call_order: list[str] = []

    async def _booked_evidence(
        portfolio_id: str,
        start_date: date,
        end_date: date,
        *,
        tenant_id: object,
    ) -> CashflowSeriesEvidence:
        call_order.append("booked")
        return CashflowSeriesEvidence(
            rows=[(start_date, Decimal("-100"))],
            latest_evidence_timestamp=datetime(2026, 3, 27, 9, tzinfo=UTC),
        )

    async def _projected_evidence(
        portfolio_id: str,
        start_date: date,
        end_date: date,
        *,
        tenant_id: object,
    ) -> CashflowSeriesEvidence:
        call_order.append("projected")
        return CashflowSeriesEvidence(
            rows=[(start_date, Decimal("-50"))],
            latest_evidence_timestamp=datetime(2026, 3, 27, 10, tzinfo=UTC),
        )

    cashflow_repo.get_portfolio_cashflow_series_with_evidence.side_effect = _booked_evidence
    cashflow_repo.get_projected_settlement_cashflow_series_with_evidence.side_effect = (
        _projected_evidence
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
        response = await service.get_liquidity_ladder(
            portfolio_id="P1", horizon_days=0, tenant_context=TEST_TENANT_CONTEXT
        )

    assert response.buckets[0].net_cashflow_portfolio_currency == Decimal("-150")
    assert response.latest_evidence_timestamp == datetime(2026, 3, 27, 10, tzinfo=UTC)
    assert call_order == ["booked", "projected"]


async def test_liquidity_ladder_reads_snapshot_and_cashflow_evidence_sequentially() -> None:
    reporting_repo = AsyncMock()
    cashflow_repo = AsyncMock()
    portfolio = _portfolio("P1")
    reporting_repo.get_portfolio_by_id.return_value = portfolio
    reporting_repo.get_latest_business_date.return_value = date(2026, 3, 27)
    call_order: list[str] = []

    async def _snapshot_rows(
        *,
        portfolio_ids: list[str],
        as_of_date: date,
    ) -> list[ReportingSnapshotRow]:
        call_order.append("snapshot")
        assert portfolio_ids == ["P1"]
        assert as_of_date == date(2026, 3, 27)
        return [
            ReportingSnapshotRow(
                portfolio=portfolio,
                snapshot=_snapshot("CASH_USD", market_value="1000"),
                instrument=_instrument("CASH_USD", asset_class="CASH", liquidity_tier=None),
            )
        ]

    async def _booked_evidence(
        portfolio_id: str,
        start_date: date,
        end_date: date,
        *,
        tenant_id: object,
    ) -> CashflowSeriesEvidence:
        call_order.append("booked")
        assert portfolio_id == "P1"
        assert start_date == date(2026, 3, 27)
        assert end_date == date(2026, 3, 27)
        return CashflowSeriesEvidence(
            rows=[(start_date, Decimal("-100"))],
            latest_evidence_timestamp=None,
        )

    async def _projected_evidence(
        portfolio_id: str,
        start_date: date,
        end_date: date,
        *,
        tenant_id: object,
    ) -> CashflowSeriesEvidence:
        call_order.append("projected")
        assert portfolio_id == "P1"
        assert start_date == date(2026, 3, 27)
        assert end_date == date(2026, 3, 27)
        return CashflowSeriesEvidence(
            rows=[(start_date, Decimal("-50"))],
            latest_evidence_timestamp=None,
        )

    reporting_repo.list_latest_snapshot_rows.side_effect = _snapshot_rows
    cashflow_repo.get_portfolio_cashflow_series_with_evidence.side_effect = _booked_evidence
    cashflow_repo.get_projected_settlement_cashflow_series_with_evidence.side_effect = (
        _projected_evidence
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
        response = await service.get_liquidity_ladder(
            portfolio_id="P1", horizon_days=0, tenant_context=TEST_TENANT_CONTEXT
        )

    assert response.buckets[0].net_cashflow_portfolio_currency == Decimal("-150")
    assert call_order == ["snapshot", "booked", "projected"]


async def test_liquidity_ladder_reads_portfolio_and_default_date_sequentially() -> None:
    reporting_repo = AsyncMock()
    cashflow_repo = AsyncMock()
    call_order: list[str] = []
    reporting_repo.list_latest_snapshot_rows.return_value = []
    cashflow_repo.get_portfolio_cashflow_series_with_evidence.return_value = CashflowSeriesEvidence(
        rows=[],
        latest_evidence_timestamp=None,
    )
    cashflow_repo.get_projected_settlement_cashflow_series_with_evidence.return_value = (
        CashflowSeriesEvidence(rows=[], latest_evidence_timestamp=None)
    )

    async def get_portfolio_by_id(portfolio_id: str, *, tenant_id: object = None):
        call_order.append("portfolio")
        assert portfolio_id == "P1"
        return _portfolio("P1")

    async def get_latest_business_date() -> date:
        call_order.append("date")
        return date(2026, 3, 27)

    reporting_repo.get_portfolio_by_id.side_effect = get_portfolio_by_id
    reporting_repo.get_latest_business_date.side_effect = get_latest_business_date

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
            portfolio_id="P1", horizon_days=0, tenant_context=TEST_TENANT_CONTEXT
        )

    assert response.resolved_as_of_date == date(2026, 3, 27)
    assert call_order == ["portfolio", "date"]


async def test_liquidity_ladder_explicit_date_skips_default_date_lookup() -> None:
    reporting_repo = AsyncMock()
    cashflow_repo = AsyncMock()
    reporting_repo.get_portfolio_by_id.return_value = _portfolio("P1")
    reporting_repo.list_latest_snapshot_rows.return_value = []
    cashflow_repo.get_portfolio_cashflow_series_with_evidence.return_value = CashflowSeriesEvidence(
        rows=[],
        latest_evidence_timestamp=None,
    )
    cashflow_repo.get_projected_settlement_cashflow_series_with_evidence.return_value = (
        CashflowSeriesEvidence(rows=[], latest_evidence_timestamp=None)
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
        response = await service.get_liquidity_ladder(
            portfolio_id="P1",
            as_of_date=date(2026, 3, 26),
            horizon_days=0,
            tenant_context=TEST_TENANT_CONTEXT,
        )

    assert response.resolved_as_of_date == date(2026, 3, 26)
    reporting_repo.get_latest_business_date.assert_not_awaited()


async def test_liquidity_ladder_raises_when_portfolio_missing() -> None:
    reporting_repo = AsyncMock()
    reporting_repo.get_portfolio_by_id.return_value = None

    with patch(
        "src.services.query_service.app.services.liquidity_ladder_service.ReportingRepository",
        return_value=reporting_repo,
    ):
        service = PortfolioLiquidityLadderService(AsyncMock(spec=AsyncSession))
        with pytest.raises(ValueError, match="Portfolio with id P404 not found"):
            await service.get_liquidity_ladder(
                portfolio_id="P404", tenant_context=TEST_TENANT_CONTEXT
            )


async def test_liquidity_ladder_rejects_invalid_horizon_before_database_access() -> None:
    service = PortfolioLiquidityLadderService(AsyncMock(spec=AsyncSession))

    with pytest.raises(
        ValueError,
        match=f"horizon_days must be between 0 and {MAX_HORIZON_DAYS}.",
    ):
        await service.get_liquidity_ladder(
            portfolio_id="P1",
            horizon_days=MAX_HORIZON_DAYS + 1,
            tenant_context=TEST_TENANT_CONTEXT,
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
            await service.get_liquidity_ladder(
                portfolio_id="P1", tenant_context=TEST_TENANT_CONTEXT
            )


async def test_liquidity_ladder_returns_unknown_quality_for_empty_source_rows() -> None:
    reporting_repo = AsyncMock()
    cashflow_repo = AsyncMock()
    portfolio = _portfolio("P1")
    reporting_repo.get_portfolio_by_id.return_value = portfolio
    reporting_repo.get_latest_business_date.return_value = date(2026, 3, 27)
    reporting_repo.list_latest_snapshot_rows.return_value = []
    cashflow_repo.get_portfolio_cashflow_series_with_evidence.return_value = CashflowSeriesEvidence(
        rows=[], latest_evidence_timestamp=None
    )
    cashflow_repo.get_projected_settlement_cashflow_series_with_evidence.return_value = (
        CashflowSeriesEvidence(rows=[], latest_evidence_timestamp=None)
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
        response = await service.get_liquidity_ladder(
            portfolio_id="P1", horizon_days=0, tenant_context=TEST_TENANT_CONTEXT
        )

    assert response.data_quality_status == "UNKNOWN"
    assert response.latest_evidence_timestamp is None
    assert response.asset_liquidity_tiers == []
    assert [bucket.bucket_code for bucket in response.buckets] == ["T0"]
    assert response.totals.opening_cash_balance_portfolio_currency is None
    assert response.totals.projected_cash_available_end_portfolio_currency is None
    assert response.totals.maximum_cash_shortfall_portfolio_currency is None
    assert response.totals.non_cash_market_value_portfolio_currency is None
    assert response.totals.non_cash_position_count is None
    empty_detail = response.degradation.details[0]
    assert empty_detail.reason_code == "SOURCE_HOLDINGS_UNAVAILABLE"
    assert empty_detail.source_as_of_date == date(2026, 3, 27)
    assert empty_detail.latest_evidence_timestamp is None


@pytest.mark.parametrize(
    (
        "market_value",
        "valuation_status",
        "expected_opening",
        "expected_end",
        "expected_shortfall",
    ),
    [
        ("0", "VALUED", Decimal("0"), Decimal("-25"), Decimal("25")),
        ("100", "VALUED_CURRENT", Decimal("100"), Decimal("75"), Decimal("0")),
        ("-100", "VALUED_STALE", Decimal("-100"), Decimal("-125"), Decimal("125")),
        (None, "UNVALUED", None, None, None),
        ("100", "FAILED", None, None, None),
        ("100", "UNVALUED", None, None, None),
    ],
)
async def test_liquidity_ladder_distinguishes_known_cash_from_unknown_valuation(
    market_value: str | None,
    valuation_status: str,
    expected_opening: Decimal | None,
    expected_end: Decimal | None,
    expected_shortfall: Decimal | None,
) -> None:
    reporting_repo = AsyncMock()
    cashflow_repo = AsyncMock()
    portfolio = _portfolio("P1")
    reporting_repo.get_portfolio_by_id.return_value = portfolio
    reporting_repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot(
                "CASH_USD",
                market_value=market_value,
                valuation_status=valuation_status,
            ),
            instrument=_instrument("CASH_USD", asset_class="CASH", liquidity_tier=None),
        )
    ]
    cashflow_repo.get_portfolio_cashflow_series_with_evidence.return_value = CashflowSeriesEvidence(
        rows=[(date(2026, 3, 27), Decimal("-25"))], latest_evidence_timestamp=None
    )
    cashflow_repo.get_projected_settlement_cashflow_series_with_evidence.return_value = (
        CashflowSeriesEvidence(rows=[], latest_evidence_timestamp=None)
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
        response = await PortfolioLiquidityLadderService(
            AsyncMock(spec=AsyncSession)
        ).get_liquidity_ladder(
            portfolio_id="P1",
            as_of_date=date(2026, 3, 27),
            horizon_days=0,
            tenant_context=TEST_TENANT_CONTEXT,
        )

    bucket = response.buckets[0]
    assert response.totals.opening_cash_balance_portfolio_currency == expected_opening
    assert response.totals.projected_cash_available_end_portfolio_currency == expected_end
    assert response.totals.maximum_cash_shortfall_portfolio_currency == expected_shortfall
    assert bucket.booked_net_cashflow_portfolio_currency == Decimal("-25")
    assert bucket.net_cashflow_portfolio_currency == Decimal("-25")
    assert bucket.cumulative_cash_available_portfolio_currency == expected_end
    assert bucket.cash_shortfall_portfolio_currency == expected_shortfall
    if expected_opening is None:
        assert response.data_quality_status == "PARTIAL"
        assert response.degradation.reason_codes == ["CASH_VALUATION_UNAVAILABLE"]
    else:
        assert response.data_quality_status == "COMPLETE"
        assert response.degradation.reason_codes == []


async def test_liquidity_ladder_preserves_carried_forward_degradation_chronology() -> None:
    reporting_repo = AsyncMock()
    cashflow_repo = AsyncMock()
    portfolio = _portfolio("P1")
    evidence_timestamp = datetime(2026, 3, 26, 8, 0, tzinfo=UTC)
    reporting_repo.get_portfolio_by_id.return_value = portfolio
    reporting_repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot(
                "CASH_USD",
                market_value="100",
                valuation_status="FAILED",
                snapshot_date=date(2026, 3, 25),
                updated_at=evidence_timestamp,
            ),
            instrument=_instrument("CASH_USD", asset_class="CASH", liquidity_tier=None),
        )
    ]
    cashflow_repo.get_portfolio_cashflow_series_with_evidence.return_value = CashflowSeriesEvidence(
        rows=[(date(2026, 3, 27), Decimal("-25"))], latest_evidence_timestamp=None
    )
    cashflow_repo.get_projected_settlement_cashflow_series_with_evidence.return_value = (
        CashflowSeriesEvidence(
            rows=[(date(2026, 3, 27), Decimal("40"))],
            latest_evidence_timestamp=None,
        )
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
        response = await PortfolioLiquidityLadderService(
            AsyncMock(spec=AsyncSession)
        ).get_liquidity_ladder(
            portfolio_id="P1",
            as_of_date=date(2026, 3, 27),
            horizon_days=0,
            tenant_context=TEST_TENANT_CONTEXT,
        )

    bucket = response.buckets[0]
    assert response.resolved_as_of_date == date(2026, 3, 27)
    assert bucket.booked_net_cashflow_portfolio_currency == Decimal("-25")
    assert bucket.projected_settlement_cashflow_portfolio_currency == Decimal("40")
    assert bucket.net_cashflow_portfolio_currency == Decimal("15")
    assert bucket.cumulative_cash_available_portfolio_currency is None
    assert bucket.cash_shortfall_portfolio_currency is None
    assert response.totals.projected_cash_available_end_portfolio_currency is None
    assert response.totals.maximum_cash_shortfall_portfolio_currency is None
    assert response.data_quality_status == "PARTIAL"
    detail = response.degradation.details[0]
    assert detail.model_dump() == {
        "section": "cash",
        "record_key": "security_id:CASH_USD",
        "affected_fields": [
            "totals.opening_cash_balance_portfolio_currency",
            "totals.projected_cash_available_end_portfolio_currency",
            "totals.maximum_cash_shortfall_portfolio_currency",
            "buckets[].opening_cash_balance_portfolio_currency",
            "buckets[].cumulative_cash_available_portfolio_currency",
            "buckets[].cash_shortfall_portfolio_currency",
        ],
        "source_kind": "UNAVAILABLE",
        "source_product_name": "HoldingsAsOf",
        "source_product_version": "v1",
        "source_as_of_date": date(2026, 3, 25),
        "latest_evidence_timestamp": evidence_timestamp,
        "freshness_status": "UNAVAILABLE",
        "reason_code": "CASH_VALUATION_UNAVAILABLE",
    }


async def test_liquidity_ladder_qualifies_failed_non_cash_with_unclassified_tier() -> None:
    reporting_repo = AsyncMock()
    cashflow_repo = AsyncMock()
    portfolio = _portfolio("P1")
    reporting_repo.get_portfolio_by_id.return_value = portfolio
    reporting_repo.get_latest_business_date.return_value = date(2026, 3, 27)
    reporting_repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot(
                "ALT1",
                market_value="500",
                valuation_status="FAILED",
                updated_at=datetime(2026, 3, 27, 8, 0, tzinfo=UTC),
            ),
            instrument=_instrument("ALT1", liquidity_tier=None),
        )
    ]
    cashflow_repo.get_portfolio_cashflow_series_with_evidence.return_value = CashflowSeriesEvidence(
        rows=[], latest_evidence_timestamp=None
    )
    cashflow_repo.get_projected_settlement_cashflow_series_with_evidence.return_value = (
        CashflowSeriesEvidence(rows=[], latest_evidence_timestamp=None)
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
        response = await service.get_liquidity_ladder(
            portfolio_id="P1", horizon_days=0, tenant_context=TEST_TENANT_CONTEXT
        )

    assert response.asset_liquidity_tiers[0].liquidity_tier == "UNCLASSIFIED"
    assert response.asset_liquidity_tiers[0].market_value_portfolio_currency is None
    assert response.totals.non_cash_market_value_portfolio_currency is None
    assert response.data_quality_status == "PARTIAL"
    assert response.degradation.reason_codes == ["NON_CASH_VALUATION_UNAVAILABLE"]
    assert response.latest_evidence_timestamp == datetime(2026, 3, 27, 8, 0, tzinfo=UTC)
    detail = response.degradation.details[0]
    assert detail.affected_fields == [
        "asset_liquidity_tiers[].market_value_portfolio_currency",
        "totals.non_cash_market_value_portfolio_currency",
    ]
    assert detail.source_product_name == "HoldingsAsOf"
    assert detail.source_product_version == "v1"
    assert detail.source_kind == "UNAVAILABLE"
    assert detail.source_as_of_date == date(2026, 3, 27)
    assert detail.latest_evidence_timestamp == datetime(2026, 3, 27, 8, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("rows", "expected_reasons", "expected_non_cash_total", "expected_non_cash_count"),
    [
        (
            [
                ("CASH_USD", "CASH", "100", None),
                ("CASH_EUR", "CASH", None, None),
                ("EQ1", "EQUITY", "200", "T1"),
            ],
            ["CASH_VALUATION_UNAVAILABLE"],
            Decimal("200"),
            1,
        ),
        (
            [
                ("CASH_USD", "CASH", "100", None),
                ("EQ1", "EQUITY", "200", "T1"),
                ("EQ2", "EQUITY", None, "T1"),
            ],
            ["NON_CASH_VALUATION_UNAVAILABLE"],
            None,
            2,
        ),
        (
            [
                ("CASH_USD", "CASH", None, None),
                ("EQ1", "EQUITY", None, "T1"),
            ],
            ["CASH_VALUATION_UNAVAILABLE", "NON_CASH_VALUATION_UNAVAILABLE"],
            None,
            1,
        ),
    ],
)
async def test_liquidity_ladder_qualifies_mixed_known_and_unknown_values(
    rows: list[tuple[str, str, str | None, str | None]],
    expected_reasons: list[str],
    expected_non_cash_total: Decimal | None,
    expected_non_cash_count: int,
) -> None:
    reporting_repo = AsyncMock()
    cashflow_repo = AsyncMock()
    portfolio = _portfolio("P1")
    reporting_repo.get_portfolio_by_id.return_value = portfolio
    reporting_repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot(security_id, market_value=market_value),
            instrument=_instrument(
                security_id,
                asset_class=asset_class,
                liquidity_tier=liquidity_tier,
            ),
        )
        for security_id, asset_class, market_value, liquidity_tier in rows
    ]
    cashflow_repo.get_portfolio_cashflow_series_with_evidence.return_value = CashflowSeriesEvidence(
        rows=[], latest_evidence_timestamp=None
    )
    cashflow_repo.get_projected_settlement_cashflow_series_with_evidence.return_value = (
        CashflowSeriesEvidence(rows=[], latest_evidence_timestamp=None)
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
        response = await PortfolioLiquidityLadderService(
            AsyncMock(spec=AsyncSession)
        ).get_liquidity_ladder(
            portfolio_id="P1",
            as_of_date=date(2026, 3, 27),
            horizon_days=0,
            tenant_context=TEST_TENANT_CONTEXT,
        )

    assert response.data_quality_status == "PARTIAL"
    assert response.degradation.reason_codes == expected_reasons
    assert response.totals.non_cash_market_value_portfolio_currency == expected_non_cash_total
    assert response.totals.non_cash_position_count == expected_non_cash_count
    if "CASH_VALUATION_UNAVAILABLE" in expected_reasons:
        assert response.totals.opening_cash_balance_portfolio_currency is None
    else:
        assert response.totals.opening_cash_balance_portfolio_currency == Decimal("100")


@pytest.mark.parametrize(
    "instrument",
    [None, _instrument("UNKNOWN1", asset_class=None), _instrument("UNKNOWN1", asset_class="  ")],
)
async def test_liquidity_ladder_does_not_assume_missing_instrument_classification_is_non_cash(
    instrument: object | None,
) -> None:
    reporting_repo = AsyncMock()
    cashflow_repo = AsyncMock()
    portfolio = _portfolio("P1")
    reporting_repo.get_portfolio_by_id.return_value = portfolio
    reporting_repo.list_latest_snapshot_rows.return_value = [
        ReportingSnapshotRow(
            portfolio=portfolio,
            snapshot=_snapshot("UNKNOWN1", market_value="500"),
            instrument=instrument,
        )
    ]
    cashflow_repo.get_portfolio_cashflow_series_with_evidence.return_value = CashflowSeriesEvidence(
        rows=[], latest_evidence_timestamp=None
    )
    cashflow_repo.get_projected_settlement_cashflow_series_with_evidence.return_value = (
        CashflowSeriesEvidence(rows=[], latest_evidence_timestamp=None)
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
        response = await PortfolioLiquidityLadderService(
            AsyncMock(spec=AsyncSession)
        ).get_liquidity_ladder(
            portfolio_id="P1",
            as_of_date=date(2026, 3, 27),
            horizon_days=0,
            tenant_context=TEST_TENANT_CONTEXT,
        )

    assert response.data_quality_status == "PARTIAL"
    assert response.degradation.reason_codes == ["INSTRUMENT_CLASSIFICATION_UNAVAILABLE"]
    assert response.totals.opening_cash_balance_portfolio_currency is None
    assert response.totals.non_cash_market_value_portfolio_currency is None
    assert response.totals.non_cash_position_count is None
    assert response.asset_liquidity_tiers == []
    detail = response.degradation.details[0]
    assert detail.affected_fields == [
        "totals.opening_cash_balance_portfolio_currency",
        "totals.projected_cash_available_end_portfolio_currency",
        "totals.maximum_cash_shortfall_portfolio_currency",
        "buckets[].opening_cash_balance_portfolio_currency",
        "buckets[].cumulative_cash_available_portfolio_currency",
        "buckets[].cash_shortfall_portfolio_currency",
        "totals.non_cash_market_value_portfolio_currency",
        "totals.non_cash_position_count",
        "asset_liquidity_tiers",
    ]
    assert detail.source_product_name == "HoldingsAsOf"
    assert detail.source_product_version == "v1"
    assert detail.source_kind == "UNAVAILABLE"
    assert detail.source_as_of_date == date(2026, 3, 27)
    assert detail.latest_evidence_timestamp is None


async def test_liquidity_ladder_partitions_cash_rows_with_single_classification_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        SimpleNamespace(instrument=SimpleNamespace(asset_class="CASH")),
        SimpleNamespace(instrument=SimpleNamespace(asset_class="EQUITY")),
        SimpleNamespace(instrument=SimpleNamespace(asset_class="BOND")),
    ]
    calls: list[object] = []

    def fake_normalize_control_code(value: object, *, default: str) -> str:
        calls.append(value)
        return str(value) if value is not None else default

    monkeypatch.setattr(
        "src.services.query_service.app.services.liquidity_ladder_service.normalize_control_code",
        fake_normalize_control_code,
    )

    cash_rows, non_cash_rows, unclassified_rows = (
        PortfolioLiquidityLadderService._partition_snapshot_rows(rows)
    )

    assert cash_rows == [rows[0]]
    assert non_cash_rows == [rows[1], rows[2]]
    assert unclassified_rows == []
    assert calls == ["CASH", "EQUITY", "BOND"]
