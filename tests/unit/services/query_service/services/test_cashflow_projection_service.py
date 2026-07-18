from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.cashflow_repository import (
    CashflowRepository,
    CashflowSeriesEvidence,
)
from src.services.query_service.app.services.cashflow_projection_service import (
    MAX_HORIZON_DAYS,
    CashflowProjectionService,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_repo() -> AsyncMock:
    repo = AsyncMock(spec=CashflowRepository)
    repo.portfolio_exists.return_value = True
    repo.get_portfolio_currency.return_value = "USD"
    repo.get_latest_business_date.return_value = date(2026, 3, 1)

    async def _series(
        portfolio_id: str, start_date: date, end_date: date
    ) -> list[tuple[date, Decimal]]:
        universe = {
            date(2026, 3, 1): Decimal("-1000"),
            date(2026, 3, 3): Decimal("250"),
        }
        return [(d, amount) for d, amount in universe.items() if start_date <= d <= end_date]

    async def _series_with_evidence(
        portfolio_id: str, start_date: date, end_date: date
    ) -> CashflowSeriesEvidence:
        rows = await _series(portfolio_id, start_date, end_date)
        return CashflowSeriesEvidence(
            rows=rows,
            latest_evidence_timestamp=datetime(2026, 3, 3, 12, 30, tzinfo=UTC),
            source_row_count=len(rows),
            source_total=sum((amount for _flow_date, amount in rows), start=Decimal("0")),
        )

    repo.get_portfolio_cashflow_series_with_evidence.side_effect = _series_with_evidence
    repo.get_projected_settlement_cashflow_series_with_evidence.return_value = (
        CashflowSeriesEvidence(rows=[], latest_evidence_timestamp=None)
    )
    return repo


async def test_projection_defaults_to_latest_business_date(mock_repo: AsyncMock):
    with patch(
        "src.services.query_service.app.services.cashflow_projection_service.CashflowRepository",
        return_value=mock_repo,
    ):
        service = CashflowProjectionService(AsyncMock(spec=AsyncSession))
        response = await service.get_cashflow_projection(portfolio_id="P1", horizon_days=10)

        mock_repo.get_portfolio_cashflow_series_with_evidence.assert_awaited_once_with(
            portfolio_id="P1",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 11),
        )
        mock_repo.get_projected_settlement_cashflow_series_with_evidence.assert_awaited_once_with(
            portfolio_id="P1",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 11),
        )
        assert response.total_net_cashflow == Decimal("-750")
        assert response.booked_total_net_cashflow == Decimal("-750")
        assert response.projected_settlement_total_cashflow == Decimal("0")
        assert response.product_name == "PortfolioCashflowProjection"
        assert response.product_version == "v1"
        assert response.portfolio_currency == "USD"
        assert response.data_quality_status == "COMPLETE"
        assert response.latest_evidence_timestamp == datetime(2026, 3, 3, 12, 30, tzinfo=UTC)
        assert response.content_hash.startswith("sha256:")
        assert response.source_batch_fingerprint == response.content_hash
        assert response.source_digest == response.content_hash
        assert response.source_refs == [
            "lotus-core://source/PortfolioCashflowProjection/P1/2026-03-01/2026-03-11"
        ]
        assert response.source_lineage["source_owner"] == "lotus-core"
        assert response.source_lineage["source_product"] == "PortfolioCashflowProjection"
        assert response.source_lineage["portfolio_id"] == "P1"
        assert response.source_lineage["input_content_hash"] == (
            response.calculation_lineage.input_content_hash
        )
        assert response.source_evidence_current is True
        assert response.freshness_status == "CURRENT"
        assert response.reconciliation_status == "COMPLETE"
        assert response.source_window_trust.source_row_count == 2
        assert response.source_window_trust.calculated_source_row_count == 2
        assert response.source_window_trust.output_group_count == 11
        assert response.source_window_trust.source_component_totals == {
            "BOOKED": Decimal("-750"),
            "PROJECTED": Decimal("0"),
        }
        assert response.source_window_trust.supportability_status == "SUPPORTED"
        assert response.request_fingerprint.startswith("cashflow_projection:")
        assert response.snapshot_id.startswith("cashflow_projection:")
        assert response.policy_version == "cashflow-projection-v1"
        assert response.calculation_lineage.algorithm_id == "PORTFOLIO_CASHFLOW_PROJECTION"
        assert response.calculation_lineage.intermediate_precision == 50
        assert response.points[0].projected_cumulative_cashflow == Decimal("-1000")
        assert response.points[0].booked_net_cashflow == Decimal("-1000")
        assert response.points[0].projected_settlement_cashflow == Decimal("0")
        assert response.points[1].net_cashflow == Decimal("0")
        assert response.points[1].projected_cumulative_cashflow == Decimal("-1000")
        assert response.points[2].projected_cumulative_cashflow == Decimal("-750")
        assert len(response.points) == 11


async def test_projection_reads_currency_and_default_date_sequentially(
    mock_repo: AsyncMock,
) -> None:
    call_order: list[str] = []

    async def get_portfolio_currency(portfolio_id: str) -> str:
        call_order.append("currency")
        assert portfolio_id == "P1"
        return "USD"

    async def get_latest_business_date() -> date:
        call_order.append("date")
        return date(2026, 3, 1)

    mock_repo.get_portfolio_currency.side_effect = get_portfolio_currency
    mock_repo.get_latest_business_date.side_effect = get_latest_business_date

    with patch(
        "src.services.query_service.app.services.cashflow_projection_service.CashflowRepository",
        return_value=mock_repo,
    ):
        service = CashflowProjectionService(AsyncMock(spec=AsyncSession))
        response = await service.get_cashflow_projection(portfolio_id="P1", horizon_days=1)

    assert response.range_start_date == date(2026, 3, 1)
    assert call_order == ["currency", "date"]


async def test_projection_booked_only_caps_to_as_of_date(mock_repo: AsyncMock):
    with patch(
        "src.services.query_service.app.services.cashflow_projection_service.CashflowRepository",
        return_value=mock_repo,
    ):
        service = CashflowProjectionService(AsyncMock(spec=AsyncSession))
        response = await service.get_cashflow_projection(
            portfolio_id="P1",
            horizon_days=10,
            as_of_date=date(2026, 3, 2),
            include_projected=False,
        )

        mock_repo.get_portfolio_cashflow_series_with_evidence.assert_awaited_once_with(
            portfolio_id="P1",
            start_date=date(2026, 3, 2),
            end_date=date(2026, 3, 2),
        )
        mock_repo.get_projected_settlement_cashflow_series_with_evidence.assert_not_awaited()
        assert response.include_projected is False
        assert response.range_end_date == date(2026, 3, 2)
        assert len(response.points) == 1
        assert response.points[0].projection_date == date(2026, 3, 2)
        assert response.points[0].net_cashflow == Decimal("0")
        assert response.notes == "Booked-only view capped at as_of_date."
        mock_repo.get_latest_business_date.assert_not_awaited()


async def test_projection_raises_when_portfolio_missing(mock_repo: AsyncMock):
    with patch(
        "src.services.query_service.app.services.cashflow_projection_service.CashflowRepository",
        return_value=mock_repo,
    ):
        mock_repo.get_portfolio_currency.return_value = None
        service = CashflowProjectionService(AsyncMock(spec=AsyncSession))
        with pytest.raises(ValueError, match="Portfolio with id P404 not found"):
            await service.get_cashflow_projection(portfolio_id="P404")


async def test_projection_rejects_unbounded_horizon_before_database_access(
    mock_repo: AsyncMock,
) -> None:
    with patch(
        "src.services.query_service.app.services.cashflow_projection_service.CashflowRepository",
        return_value=mock_repo,
    ):
        service = CashflowProjectionService(AsyncMock(spec=AsyncSession))

        with pytest.raises(
            ValueError,
            match=f"horizon_days must be between 1 and {MAX_HORIZON_DAYS}.",
        ):
            await service.get_cashflow_projection(
                portfolio_id="P1",
                horizon_days=MAX_HORIZON_DAYS + 1,
            )

    mock_repo.get_portfolio_currency.assert_not_awaited()


async def test_projection_includes_future_settlement_dated_external_flows(mock_repo: AsyncMock):
    mock_repo.get_projected_settlement_cashflow_series_with_evidence.return_value = (
        CashflowSeriesEvidence(
            rows=[(date(2026, 3, 4), Decimal("-18000"))],
            latest_evidence_timestamp=datetime(2026, 3, 4, 9, tzinfo=UTC),
            source_row_count=1,
            source_total=Decimal("-18000"),
        )
    )

    with patch(
        "src.services.query_service.app.services.cashflow_projection_service.CashflowRepository",
        return_value=mock_repo,
    ):
        service = CashflowProjectionService(AsyncMock(spec=AsyncSession))
        response = await service.get_cashflow_projection(
            portfolio_id="P1",
            horizon_days=4,
            as_of_date=date(2026, 3, 1),
            include_projected=True,
        )

        points = {point.projection_date: point for point in response.points}
        assert points[date(2026, 3, 4)].net_cashflow == Decimal("-18000")
        assert points[date(2026, 3, 4)].booked_net_cashflow == Decimal("0")
        assert points[date(2026, 3, 4)].projected_settlement_cashflow == Decimal("-18000")
        assert points[date(2026, 3, 4)].projected_cumulative_cashflow == Decimal("-18750")
        assert response.total_net_cashflow == Decimal("-18750")
        assert response.booked_total_net_cashflow == Decimal("-750")
        assert response.projected_settlement_total_cashflow == Decimal("-18000")
        assert (
            response.notes
            == "Projected window includes settlement-dated future external cash movements."
        )


async def test_projection_adds_same_day_booked_and_projected_movements(
    mock_repo: AsyncMock,
) -> None:
    mock_repo.get_portfolio_cashflow_series_with_evidence.side_effect = None
    mock_repo.get_portfolio_cashflow_series_with_evidence.return_value = CashflowSeriesEvidence(
        rows=[(date(2026, 3, 2), Decimal("400.25"))],
        latest_evidence_timestamp=datetime(2026, 3, 2, 9, tzinfo=UTC),
        source_row_count=1,
        source_total=Decimal("400.25"),
    )
    mock_repo.get_projected_settlement_cashflow_series_with_evidence.return_value = (
        CashflowSeriesEvidence(
            rows=[(date(2026, 3, 2), Decimal("-150.10"))],
            latest_evidence_timestamp=datetime(2026, 3, 2, 10, tzinfo=UTC),
            source_row_count=1,
            source_total=Decimal("-150.10"),
        )
    )

    with patch(
        "src.services.query_service.app.services.cashflow_projection_service.CashflowRepository",
        return_value=mock_repo,
    ):
        service = CashflowProjectionService(AsyncMock(spec=AsyncSession))
        response = await service.get_cashflow_projection(
            portfolio_id="P1",
            horizon_days=2,
            as_of_date=date(2026, 3, 1),
            include_projected=True,
        )

        points = {point.projection_date: point for point in response.points}
        assert points[date(2026, 3, 1)].net_cashflow == Decimal("0")
        assert points[date(2026, 3, 1)].booked_net_cashflow == Decimal("0")
        assert points[date(2026, 3, 1)].projected_settlement_cashflow == Decimal("0")
        assert points[date(2026, 3, 2)].net_cashflow == Decimal("250.15")
        assert points[date(2026, 3, 2)].booked_net_cashflow == Decimal("400.25")
        assert points[date(2026, 3, 2)].projected_settlement_cashflow == Decimal("-150.10")
        assert points[date(2026, 3, 2)].projected_cumulative_cashflow == Decimal("250.15")
        assert points[date(2026, 3, 3)].projected_cumulative_cashflow == Decimal("250.15")
        assert response.total_net_cashflow == Decimal("250.15")
        assert response.booked_total_net_cashflow == Decimal("400.25")
    assert response.projected_settlement_total_cashflow == Decimal("-150.10")


async def test_projection_runs_booked_and_projected_reads_sequentially(
    mock_repo: AsyncMock,
) -> None:
    call_order: list[str] = []

    async def _booked_evidence(
        portfolio_id: str,
        start_date: date,
        end_date: date,
    ) -> CashflowSeriesEvidence:
        call_order.append("booked")
        return CashflowSeriesEvidence(
            rows=[(start_date, Decimal("10"))],
            latest_evidence_timestamp=datetime(2026, 3, 1, 9, tzinfo=UTC),
            source_row_count=1,
            source_total=Decimal("10"),
        )

    async def _projected_evidence(
        portfolio_id: str,
        start_date: date,
        end_date: date,
    ) -> CashflowSeriesEvidence:
        call_order.append("projected")
        return CashflowSeriesEvidence(
            rows=[(start_date, Decimal("-2"))],
            latest_evidence_timestamp=datetime(2026, 3, 1, 10, tzinfo=UTC),
            source_row_count=1,
            source_total=Decimal("-2"),
        )

    mock_repo.get_portfolio_cashflow_series_with_evidence.side_effect = _booked_evidence
    mock_repo.get_projected_settlement_cashflow_series_with_evidence.side_effect = (
        _projected_evidence
    )

    with patch(
        "src.services.query_service.app.services.cashflow_projection_service.CashflowRepository",
        return_value=mock_repo,
    ):
        service = CashflowProjectionService(AsyncMock(spec=AsyncSession))
        response = await service.get_cashflow_projection(
            portfolio_id="P1",
            horizon_days=1,
            as_of_date=date(2026, 3, 1),
            include_projected=True,
        )

    assert response.total_net_cashflow == Decimal("8")
    assert response.latest_evidence_timestamp == datetime(2026, 3, 1, 10, tzinfo=UTC)
    assert call_order == ["booked", "projected"]


async def test_projection_sum_by_date_treats_blank_and_null_amounts_as_zero() -> None:
    totals = CashflowProjectionService._sum_by_date(
        [
            (date(2026, 3, 2), Decimal("400.25")),
            (date(2026, 3, 2), " "),
            (date(2026, 3, 2), None),
        ]
    )

    assert totals == {date(2026, 3, 2): Decimal("400.25")}


async def test_projection_fails_closed_when_source_total_does_not_reconcile(
    mock_repo: AsyncMock,
) -> None:
    mock_repo.get_portfolio_cashflow_series_with_evidence.side_effect = None
    mock_repo.get_portfolio_cashflow_series_with_evidence.return_value = CashflowSeriesEvidence(
        rows=[(date(2026, 3, 1), Decimal("10"))],
        latest_evidence_timestamp=datetime(2026, 3, 1, 9, tzinfo=UTC),
        source_row_count=1,
        source_total=Decimal("11"),
    )

    with patch(
        "src.services.query_service.app.services.cashflow_projection_service.CashflowRepository",
        return_value=mock_repo,
    ):
        response = await CashflowProjectionService(
            AsyncMock(spec=AsyncSession)
        ).get_cashflow_projection(
            portfolio_id="P1",
            horizon_days=1,
            as_of_date=date(2026, 3, 1),
        )

    assert response.reconciliation_status == "BLOCKED"
    assert response.data_quality_status == "BLOCKED"
    assert response.source_evidence_current is False
    assert response.source_window_trust.reason_codes == ["SOURCE_TOTAL_MISMATCH"]


async def test_projection_binds_tenant_to_input_calculation_and_output_identity(
    mock_repo: AsyncMock,
) -> None:
    with patch(
        "src.services.query_service.app.services.cashflow_projection_service.CashflowRepository",
        return_value=mock_repo,
    ):
        service = CashflowProjectionService(AsyncMock(spec=AsyncSession))
        tenant_a = await service.get_cashflow_projection(
            portfolio_id="P1", horizon_days=1, tenant_id=" tenant-a "
        )
        tenant_b = await service.get_cashflow_projection(
            portfolio_id="P1", horizon_days=1, tenant_id="tenant-b"
        )

    assert tenant_a.tenant_id == "tenant-a"
    assert tenant_a.calculation_lineage.input_content_hash != (
        tenant_b.calculation_lineage.input_content_hash
    )
    assert tenant_a.content_hash != tenant_b.content_hash
    assert tenant_a.snapshot_id != tenant_b.snapshot_id
