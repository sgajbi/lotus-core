import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from portfolio_common.reconciliation_quality import COMPLETE
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.cashflow_projection_dto import CashflowProjectionPoint, CashflowProjectionResponse
from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from ..repositories.cashflow_repository import CashflowRepository

logger = logging.getLogger(__name__)


class CashflowProjectionService:
    """Builds booked/projection cashflow windows for portfolio operations."""

    def __init__(self, db: AsyncSession):
        self.repo = CashflowRepository(db)

    async def get_cashflow_projection(
        self,
        portfolio_id: str,
        horizon_days: int = 10,
        as_of_date: Optional[date] = None,
        include_projected: bool = True,
    ) -> CashflowProjectionResponse:
        portfolio_currency = await self.repo.get_portfolio_currency(portfolio_id)
        if portfolio_currency is None:
            raise ValueError(f"Portfolio with id {portfolio_id} not found")

        effective_as_of_date = as_of_date
        if effective_as_of_date is None:
            effective_as_of_date = await self.repo.get_latest_business_date() or date.today()

        range_start_date = effective_as_of_date
        range_end_date = effective_as_of_date + timedelta(days=horizon_days)
        query_end_date = range_end_date if include_projected else effective_as_of_date

        rows = await self.repo.get_portfolio_cashflow_series(
            portfolio_id=portfolio_id,
            start_date=range_start_date,
            end_date=query_end_date,
        )
        projected_rows = []
        if include_projected:
            projected_rows = await self.repo.get_projected_settlement_cashflow_series(
                portfolio_id=portfolio_id,
                start_date=range_start_date,
                end_date=query_end_date,
            )
        latest_evidence_timestamp = await self.repo.get_latest_cashflow_evidence_timestamp(
            portfolio_id=portfolio_id,
            start_date=range_start_date,
            end_date=query_end_date,
            include_projected=include_projected,
        )

        booked_by_date = self._sum_by_date(rows)
        projected_by_date = self._sum_by_date(projected_rows)
        booked_total = Decimal("0")
        projected_total = Decimal("0")
        running = Decimal("0")
        points: list[CashflowProjectionPoint] = []
        cursor = range_start_date
        while cursor <= query_end_date:
            booked_amount = booked_by_date.get(cursor, Decimal("0"))
            projected_amount = projected_by_date.get(cursor, Decimal("0"))
            net_amount = booked_amount + projected_amount
            booked_total += booked_amount
            projected_total += projected_amount
            running += net_amount
            points.append(
                CashflowProjectionPoint(
                    projection_date=cursor,
                    booked_net_cashflow=booked_amount,
                    projected_settlement_cashflow=projected_amount,
                    net_cashflow=net_amount,
                    projected_cumulative_cashflow=running,
                )
            )
            cursor += timedelta(days=1)

        return CashflowProjectionResponse(
            portfolio_id=portfolio_id,
            range_start_date=range_start_date,
            range_end_date=query_end_date,
            include_projected=include_projected,
            portfolio_currency=portfolio_currency,
            points=points,
            total_net_cashflow=running,
            booked_total_net_cashflow=booked_total,
            projected_settlement_total_cashflow=projected_total,
            projection_days=horizon_days,
            notes=(
                "Projected window includes settlement-dated future external cash movements."
                if include_projected
                else "Booked-only view capped at as_of_date."
            ),
            **source_data_product_runtime_metadata(
                as_of_date=effective_as_of_date,
                data_quality_status=COMPLETE,
                latest_evidence_timestamp=latest_evidence_timestamp,
                source_batch_fingerprint=(
                    "cashflow_projection:"
                    f"{portfolio_id}:{effective_as_of_date}:{query_end_date}:"
                    f"include_projected={str(include_projected).lower()}"
                ),
            ),
        )

    @staticmethod
    def _sum_by_date(rows: list[tuple[date, Decimal]]) -> dict[date, Decimal]:
        totals: dict[date, Decimal] = {}
        for flow_date, amount in rows:
            totals[flow_date] = totals.get(flow_date, Decimal("0")) + Decimal(str(amount))
        return totals
