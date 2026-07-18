from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.cashflow_repository import (
    CashflowRepository,
    CashMovementSummaryEvidence,
)
from src.services.query_service.app.services.cash_movement_service import CashMovementService

pytestmark = pytest.mark.asyncio


class _StringCountedAmount:
    def __init__(self, raw: str) -> None:
        self.raw = raw
        self.stringify_count = 0

    def __str__(self) -> str:
        self.stringify_count += 1
        return self.raw


@pytest.fixture
def mock_repo() -> AsyncMock:
    repo = AsyncMock(spec=CashflowRepository)
    repo.get_portfolio_currency.return_value = "USD"
    repo.get_portfolio_cash_movement_summary.return_value = CashMovementSummaryEvidence(
        rows=[
            (
                "CASHFLOW_IN",
                "SETTLED",
                "USD",
                False,
                True,
                2,
                Decimal("12500.00"),
                datetime(2026, 3, 5, 12, 30, tzinfo=UTC),
            ),
            (
                "TRADE_SETTLEMENT",
                "SETTLED",
                "USD",
                True,
                False,
                1,
                Decimal("-3500.00"),
                datetime(2026, 3, 6, 9, 15, tzinfo=UTC),
            ),
        ],
        source_row_count=3,
        source_currency_totals={"USD": Decimal("9000.00")},
    )
    return repo


async def test_cash_movement_summary_preserves_source_buckets(mock_repo: AsyncMock) -> None:
    with patch(
        "src.services.query_service.app.services.cash_movement_service.CashflowRepository",
        return_value=mock_repo,
    ):
        service = CashMovementService(AsyncMock(spec=AsyncSession))
        response = await service.get_cash_movement_summary(
            portfolio_id="P1",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        )

    mock_repo.get_portfolio_cash_movement_summary.assert_awaited_once_with(
        portfolio_id="P1",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
    )
    assert response.product_name == "PortfolioCashMovementSummary"
    assert response.product_version == "v1"
    assert response.portfolio_currency == "USD"
    assert response.as_of_date == date(2026, 3, 31)
    assert response.data_quality_status == "COMPLETE"
    assert response.cashflow_count == 3
    assert response.latest_evidence_timestamp == datetime(2026, 3, 6, 9, 15, tzinfo=UTC)
    assert response.source_batch_fingerprint.startswith("sha256:")
    assert response.source_batch_fingerprint == response.content_hash
    assert response.freshness_status == "CURRENT"
    assert response.reconciliation_status == "COMPLETE"
    assert response.source_window_trust.source_row_count == 3
    assert response.source_window_trust.calculated_source_row_count == 3
    assert response.source_window_trust.source_component_totals == {
        "USD": Decimal("9000.00")
    }
    assert response.request_fingerprint.startswith("cash_movement_summary:")
    assert response.snapshot_id.startswith("cash_movement_summary:")
    assert response.policy_version == "cash-movement-summary-v1"
    assert response.calculation_lineage.algorithm_id == "PORTFOLIO_CASH_MOVEMENT_SUMMARY"
    assert response.buckets[0].movement_direction == "INFLOW"
    assert response.buckets[1].movement_direction == "OUTFLOW"
    assert response.buckets[1].is_position_flow is True
    assert "not a forecast" in response.notes


async def test_cash_movement_summary_converts_bucket_amount_once(mock_repo: AsyncMock) -> None:
    counted_amount = _StringCountedAmount("-2500.00")
    mock_repo.get_portfolio_cash_movement_summary.return_value = CashMovementSummaryEvidence(
        rows=[
            (
                "TRADE_SETTLEMENT",
                "SETTLED",
                "USD",
                True,
                False,
                1,
                counted_amount,
                datetime(2026, 3, 6, 9, 15, tzinfo=UTC),
            )
        ],
        source_row_count=1,
        source_currency_totals={"USD": Decimal("-2500.00")},
    )

    with patch(
        "src.services.query_service.app.services.cash_movement_service.CashflowRepository",
        return_value=mock_repo,
    ):
        service = CashMovementService(AsyncMock(spec=AsyncSession))
        response = await service.get_cash_movement_summary(
            portfolio_id="P1",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        )

    assert response.buckets[0].total_amount == Decimal("-2500.00")
    assert response.buckets[0].movement_direction == "OUTFLOW"
    assert counted_amount.stringify_count == 1


async def test_cash_movement_summary_marks_empty_window_current(mock_repo: AsyncMock) -> None:
    mock_repo.get_portfolio_cash_movement_summary.return_value = CashMovementSummaryEvidence(
        rows=[], source_row_count=0, source_currency_totals={}
    )

    with patch(
        "src.services.query_service.app.services.cash_movement_service.CashflowRepository",
        return_value=mock_repo,
    ):
        service = CashMovementService(AsyncMock(spec=AsyncSession))
        response = await service.get_cash_movement_summary(
            portfolio_id="P1",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        )

    assert response.buckets == []
    assert response.cashflow_count == 0
    assert response.data_quality_status == "COMPLETE"
    assert response.latest_evidence_timestamp is None
    assert response.source_evidence_current is True
    assert response.freshness_status == "CURRENT"
    assert response.source_window_trust.window_status == "EMPTY"
    assert response.source_window_trust.reason_codes == ["EMPTY_SOURCE_WINDOW"]


async def test_cash_movement_summary_rejects_invalid_window(mock_repo: AsyncMock) -> None:
    with patch(
        "src.services.query_service.app.services.cash_movement_service.CashflowRepository",
        return_value=mock_repo,
    ):
        service = CashMovementService(AsyncMock(spec=AsyncSession))
        with pytest.raises(ValueError, match="start_date must be on or before end_date"):
            await service.get_cash_movement_summary(
                portfolio_id="P1",
                start_date=date(2026, 4, 1),
                end_date=date(2026, 3, 31),
            )

    mock_repo.get_portfolio_cash_movement_summary.assert_not_awaited()


async def test_cash_movement_summary_rejects_excessive_window(mock_repo: AsyncMock) -> None:
    with patch(
        "src.services.query_service.app.services.cash_movement_service.CashflowRepository",
        return_value=mock_repo,
    ):
        service = CashMovementService(AsyncMock(spec=AsyncSession))
        with pytest.raises(ValueError, match="date window must be 366 days or less"):
            await service.get_cash_movement_summary(
                portfolio_id="P1",
                start_date=date(2026, 1, 1),
                end_date=date(2027, 1, 2),
            )

    mock_repo.get_portfolio_currency.assert_not_awaited()
    mock_repo.get_portfolio_cash_movement_summary.assert_not_awaited()


async def test_cash_movement_summary_raises_when_portfolio_missing(
    mock_repo: AsyncMock,
) -> None:
    mock_repo.get_portfolio_currency.return_value = None

    with patch(
        "src.services.query_service.app.services.cash_movement_service.CashflowRepository",
        return_value=mock_repo,
    ):
        service = CashMovementService(AsyncMock(spec=AsyncSession))
        with pytest.raises(ValueError, match="Portfolio with id P404 not found"):
            await service.get_cash_movement_summary(
                portfolio_id="P404",
                start_date=date(2026, 3, 1),
                end_date=date(2026, 3, 31),
            )


async def test_cash_movement_summary_fails_closed_on_count_and_currency_total_mismatch(
    mock_repo: AsyncMock,
) -> None:
    evidence = mock_repo.get_portfolio_cash_movement_summary.return_value
    mock_repo.get_portfolio_cash_movement_summary.return_value = CashMovementSummaryEvidence(
        rows=evidence.rows,
        source_row_count=4,
        source_currency_totals={"USD": Decimal("9001")},
    )

    with patch(
        "src.services.query_service.app.services.cash_movement_service.CashflowRepository",
        return_value=mock_repo,
    ):
        response = await CashMovementService(
            AsyncMock(spec=AsyncSession)
        ).get_cash_movement_summary(
            portfolio_id="P1",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        )

    assert response.reconciliation_status == "BLOCKED"
    assert response.data_quality_status == "BLOCKED"
    assert response.source_evidence_current is False
    assert response.source_window_trust.reason_codes == [
        "SOURCE_COUNT_MISMATCH",
        "SOURCE_TOTAL_MISMATCH",
    ]


async def test_cash_movement_summary_binds_tenant_to_calculation_identity(
    mock_repo: AsyncMock,
) -> None:
    with patch(
        "src.services.query_service.app.services.cash_movement_service.CashflowRepository",
        return_value=mock_repo,
    ):
        service = CashMovementService(AsyncMock(spec=AsyncSession))
        tenant_a = await service.get_cash_movement_summary(
            portfolio_id="P1",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
            tenant_id=" tenant-a ",
        )
        tenant_b = await service.get_cash_movement_summary(
            portfolio_id="P1",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
            tenant_id="tenant-b",
        )

    assert tenant_a.tenant_id == "tenant-a"
    assert tenant_a.calculation_lineage.input_content_hash != (
        tenant_b.calculation_lineage.input_content_hash
    )
    assert tenant_a.content_hash != tenant_b.content_hash
