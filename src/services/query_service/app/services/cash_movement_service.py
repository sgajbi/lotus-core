from datetime import date
from decimal import Decimal

from portfolio_common.reconciliation_quality import COMPLETE
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.cash_movement_dto import CashMovementBucket, PortfolioCashMovementSummaryResponse
from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from ..repositories.cashflow_repository import CashflowRepository


class CashMovementService:
    """Builds source-owned cash movement summaries from latest cashflow rows."""

    def __init__(self, db: AsyncSession):
        self.repo = CashflowRepository(db)

    async def get_cash_movement_summary(
        self,
        portfolio_id: str,
        start_date: date,
        end_date: date,
    ) -> PortfolioCashMovementSummaryResponse:
        if start_date > end_date:
            raise ValueError("start_date must be on or before end_date")

        portfolio_currency = await self.repo.get_portfolio_currency(portfolio_id)
        if portfolio_currency is None:
            raise ValueError(f"Portfolio with id {portfolio_id} not found")

        rows = await self.repo.get_portfolio_cash_movement_summary(
            portfolio_id=portfolio_id,
            start_date=start_date,
            end_date=end_date,
        )
        buckets = [
            CashMovementBucket(
                classification=classification,
                timing=timing,
                currency=currency,
                is_position_flow=is_position_flow,
                is_portfolio_flow=is_portfolio_flow,
                cashflow_count=int(cashflow_count or 0),
                total_amount=Decimal(str(total_amount or 0)),
                movement_direction=self._movement_direction(Decimal(str(total_amount or 0))),
            )
            for (
                classification,
                timing,
                currency,
                is_position_flow,
                is_portfolio_flow,
                cashflow_count,
                total_amount,
                _latest_timestamp,
            ) in rows
        ]
        cashflow_count = sum(bucket.cashflow_count for bucket in buckets)
        latest_evidence_timestamp = max(
            (row[7] for row in rows if row[7] is not None),
            default=None,
        )

        return PortfolioCashMovementSummaryResponse(
            portfolio_id=portfolio_id,
            start_date=start_date,
            end_date=end_date,
            buckets=buckets,
            cashflow_count=cashflow_count,
            notes=(
                "Summary aggregates latest cashflow rows by classification, timing, currency, "
                "and flow scope. It is not a forecast, funding recommendation, treasury "
                "instruction, or OMS acknowledgement."
            ),
            **source_data_product_runtime_metadata(
                as_of_date=end_date,
                data_quality_status=COMPLETE if cashflow_count else "MISSING",
                latest_evidence_timestamp=latest_evidence_timestamp,
                source_batch_fingerprint=(
                    f"cash_movement_summary:{portfolio_id}:{start_date}:{end_date}"
                ),
            ),
        )

    @staticmethod
    def _movement_direction(amount: Decimal) -> str:
        if amount > 0:
            return "INFLOW"
        if amount < 0:
            return "OUTFLOW"
        return "FLAT"
