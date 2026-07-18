import logging
from datetime import date, timedelta
from decimal import Decimal, localcontext
from typing import Optional

from portfolio_common.domain.calculation_lineage import build_calculation_lineage
from portfolio_common.source_data_product_metadata import (
    source_data_product_runtime_metadata,
    stable_content_hash,
)
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.strict_decimal import decimal_or_zero
from ..dtos.cashflow_projection_dto import CashflowProjectionPoint, CashflowProjectionResponse
from ..repositories.cashflow_repository import CashflowRepository
from .cashflow_evidence_window import read_cashflow_evidence_window
from .cashflow_product_trust import reconcile_cashflow_window

logger = logging.getLogger(__name__)

DEFAULT_HORIZON_DAYS = 10
MAX_HORIZON_DAYS = 366
CASHFLOW_PROJECTION_ALGORITHM_ID = "PORTFOLIO_CASHFLOW_PROJECTION"
CASHFLOW_PROJECTION_ALGORITHM_VERSION = 1
CASHFLOW_PROJECTION_INTERMEDIATE_PRECISION = 50
CASHFLOW_PROJECTION_POLICY_VERSION = "cashflow-projection-v1"


class CashflowProjectionService:
    """Builds booked/projection cashflow windows for portfolio operations."""

    def __init__(self, db: AsyncSession):
        self.repo = CashflowRepository(db)

    async def get_cashflow_projection(
        self,
        portfolio_id: str,
        horizon_days: int = DEFAULT_HORIZON_DAYS,
        as_of_date: Optional[date] = None,
        include_projected: bool = True,
        tenant_id: str | None = None,
    ) -> CashflowProjectionResponse:
        if horizon_days < 1 or horizon_days > MAX_HORIZON_DAYS:
            raise ValueError(f"horizon_days must be between 1 and {MAX_HORIZON_DAYS}.")

        portfolio_currency = await self.repo.get_portfolio_currency(portfolio_id)
        if portfolio_currency is None:
            raise ValueError(f"Portfolio with id {portfolio_id} not found")
        default_as_of_date = (
            await self.repo.get_latest_business_date() if as_of_date is None else as_of_date
        )

        effective_as_of_date = default_as_of_date or date.today()

        range_start_date = effective_as_of_date
        range_end_date = effective_as_of_date + timedelta(days=horizon_days)
        query_end_date = range_end_date if include_projected else effective_as_of_date

        cashflow_evidence = await read_cashflow_evidence_window(
            repo=self.repo,
            portfolio_id=portfolio_id,
            start_date=range_start_date,
            end_date=query_end_date,
            include_projected=include_projected,
        )

        with localcontext() as calculation_context:
            calculation_context.prec = CASHFLOW_PROJECTION_INTERMEDIATE_PRECISION
            booked_by_date = self._sum_by_date(cashflow_evidence.booked_rows)
            projected_by_date = self._sum_by_date(cashflow_evidence.projected_rows)
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

        normalized_tenant_id = tenant_id.strip() if tenant_id and tenant_id.strip() else None
        source_row_count = (
            cashflow_evidence.booked_source_row_count
            + cashflow_evidence.projected_source_row_count
        )
        source_component_totals = {
            "BOOKED": cashflow_evidence.booked_source_total,
            "PROJECTED": cashflow_evidence.projected_source_total,
        }
        calculated_component_totals = {
            "BOOKED": booked_total,
            "PROJECTED": projected_total,
        }
        source_window_trust = reconcile_cashflow_window(
            source_row_count=source_row_count,
            calculated_source_row_count=source_row_count,
            output_group_count=len(points),
            source_component_totals=source_component_totals,
            calculated_component_totals=calculated_component_totals,
            latest_evidence_timestamp=cashflow_evidence.latest_evidence_timestamp,
        )
        response_values = {
            "portfolio_id": portfolio_id,
            "range_start_date": range_start_date,
            "range_end_date": query_end_date,
            "include_projected": include_projected,
            "portfolio_currency": portfolio_currency,
            "points": [point.model_dump(mode="python") for point in points],
            "total_net_cashflow": running,
            "booked_total_net_cashflow": booked_total,
            "projected_settlement_total_cashflow": projected_total,
            "projection_days": horizon_days,
            "source_window_trust": source_window_trust.response.model_dump(mode="python"),
        }
        calculation_lineage = build_calculation_lineage(
            algorithm_id=CASHFLOW_PROJECTION_ALGORITHM_ID,
            algorithm_version=CASHFLOW_PROJECTION_ALGORITHM_VERSION,
            intermediate_precision=CASHFLOW_PROJECTION_INTERMEDIATE_PRECISION,
            input_payload={
                "portfolio_id": portfolio_id,
                "tenant_id": normalized_tenant_id,
                "as_of_date": effective_as_of_date,
                "range_start_date": range_start_date,
                "range_end_date": query_end_date,
                "include_projected": include_projected,
                "portfolio_currency": portfolio_currency,
                "booked_rows": cashflow_evidence.booked_rows,
                "projected_rows": cashflow_evidence.projected_rows,
                "source_row_count": source_row_count,
                "source_component_totals": source_component_totals,
                "latest_evidence_timestamp": cashflow_evidence.latest_evidence_timestamp,
            },
            output_payload=response_values,
        )
        request_fingerprint = (
            f"cashflow_projection:{calculation_lineage.input_content_hash[:16]}"
        )

        source_ref = (
            "lotus-core://source/PortfolioCashflowProjection/"
            f"{portfolio_id}/{effective_as_of_date.isoformat()}/{query_end_date.isoformat()}"
        )
        content_hash = stable_content_hash(
            {
                "product_name": "PortfolioCashflowProjection",
                "product_version": "v1",
                "portfolio_id": portfolio_id,
                "tenant_id": normalized_tenant_id,
                "as_of_date": effective_as_of_date,
                "range_start_date": range_start_date,
                "range_end_date": query_end_date,
                "include_projected": include_projected,
                "portfolio_currency": portfolio_currency,
                "request_fingerprint": request_fingerprint,
                "response_values": response_values,
                "calculation_lineage": calculation_lineage.lineage_payload(),
                "latest_evidence_timestamp": cashflow_evidence.latest_evidence_timestamp,
            }
        )
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
            request_fingerprint=request_fingerprint,
            source_window_trust=source_window_trust.response,
            calculation_lineage=calculation_lineage.lineage_payload(),
            notes=(
                "Projected window includes settlement-dated future external cash movements."
                if include_projected
                else "Booked-only view capped at as_of_date."
            ),
            **source_data_product_runtime_metadata(
                as_of_date=effective_as_of_date,
                tenant_id=normalized_tenant_id,
                reconciliation_status=source_window_trust.reconciliation_status,
                data_quality_status=source_window_trust.data_quality_status,
                latest_evidence_timestamp=cashflow_evidence.latest_evidence_timestamp,
                source_batch_fingerprint=(
                    "cashflow_projection:"
                    f"{portfolio_id}:{effective_as_of_date}:{query_end_date}:"
                    f"include_projected={str(include_projected).lower()}"
                ),
                content_hash=content_hash,
                snapshot_id=(
                    "cashflow_projection:"
                    f"{calculation_lineage.output_content_hash[:24]}"
                ),
                policy_version=CASHFLOW_PROJECTION_POLICY_VERSION,
                source_refs=[source_ref],
                lineage={
                    "source_owner": "lotus-core",
                    "source_product": "PortfolioCashflowProjection",
                    "portfolio_id": portfolio_id,
                    "input_content_hash": calculation_lineage.input_content_hash,
                    "calculation_content_hash": calculation_lineage.calculation_content_hash,
                    "output_content_hash": calculation_lineage.output_content_hash,
                    "algorithm_id": calculation_lineage.algorithm_id,
                    "algorithm_version": str(calculation_lineage.algorithm_version),
                },
                source_evidence_current=source_window_trust.source_evidence_current,
                freshness_status=source_window_trust.freshness_status,
                use_content_hash_as_source_batch_fingerprint=True,
            ),
        )

    @staticmethod
    def _sum_by_date(rows: list[tuple[date, Decimal]]) -> dict[date, Decimal]:
        totals: dict[date, Decimal] = {}
        for flow_date, amount in rows:
            totals[flow_date] = totals.get(flow_date, Decimal("0")) + decimal_or_zero(amount)
        return totals
