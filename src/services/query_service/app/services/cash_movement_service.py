from datetime import date
from decimal import Decimal, localcontext

from portfolio_common.domain.calculation_lineage import build_calculation_lineage
from portfolio_common.source_data_product_metadata import (
    source_data_product_runtime_metadata,
    stable_content_hash,
)
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.strict_decimal import decimal_or_zero
from ..dtos.cash_movement_dto import CashMovementBucket, PortfolioCashMovementSummaryResponse
from ..repositories.cashflow_repository import CashflowRepository
from .cashflow_product_trust import reconcile_cashflow_window

MAX_CASH_MOVEMENT_WINDOW_DAYS = 366
CASH_MOVEMENT_ALGORITHM_ID = "PORTFOLIO_CASH_MOVEMENT_SUMMARY"
CASH_MOVEMENT_ALGORITHM_VERSION = 1
CASH_MOVEMENT_INTERMEDIATE_PRECISION = 50
CASH_MOVEMENT_POLICY_VERSION = "cash-movement-summary-v1"


class CashMovementService:
    """Builds source-owned cash movement summaries from latest cashflow rows."""

    def __init__(self, db: AsyncSession):
        self.repo = CashflowRepository(db)

    async def get_cash_movement_summary(
        self,
        portfolio_id: str,
        start_date: date,
        end_date: date,
        tenant_id: str | None = None,
    ) -> PortfolioCashMovementSummaryResponse:
        if start_date > end_date:
            raise ValueError("start_date must be on or before end_date")
        window_days = (end_date - start_date).days + 1
        if window_days > MAX_CASH_MOVEMENT_WINDOW_DAYS:
            raise ValueError(
                "cash movement summary date window must be "
                f"{MAX_CASH_MOVEMENT_WINDOW_DAYS} days or less"
            )

        portfolio_currency = await self.repo.get_portfolio_currency(portfolio_id)
        if portfolio_currency is None:
            raise ValueError(f"Portfolio with id {portfolio_id} not found")

        evidence = await self.repo.get_portfolio_cash_movement_summary(
            portfolio_id=portfolio_id,
            start_date=start_date,
            end_date=end_date,
        )
        rows = evidence.rows
        buckets: list[CashMovementBucket] = []
        normalized_source_rows: list[dict[str, object]] = []
        for (
            classification,
            timing,
            currency,
            is_position_flow,
            is_portfolio_flow,
            cashflow_count,
            total_amount,
            _latest_timestamp,
        ) in rows:
            resolved_total_amount = decimal_or_zero(total_amount)
            normalized_source_rows.append(
                {
                    "classification": classification,
                    "timing": timing,
                    "currency": currency,
                    "is_position_flow": is_position_flow,
                    "is_portfolio_flow": is_portfolio_flow,
                    "cashflow_count": int(cashflow_count or 0),
                    "total_amount": resolved_total_amount,
                    "latest_evidence_timestamp": _latest_timestamp,
                }
            )
            buckets.append(
                CashMovementBucket(
                    classification=classification,
                    timing=timing,
                    currency=currency,
                    is_position_flow=is_position_flow,
                    is_portfolio_flow=is_portfolio_flow,
                    cashflow_count=int(cashflow_count or 0),
                    total_amount=resolved_total_amount,
                    movement_direction=self._movement_direction(resolved_total_amount),
                )
            )
        cashflow_count = sum(bucket.cashflow_count for bucket in buckets)
        with localcontext() as calculation_context:
            calculation_context.prec = CASH_MOVEMENT_INTERMEDIATE_PRECISION
            calculated_currency_totals: dict[str, Decimal] = {}
            for bucket in buckets:
                calculated_currency_totals[bucket.currency] = (
                    calculated_currency_totals.get(bucket.currency, Decimal("0"))
                    + bucket.total_amount
                )
        latest_evidence_timestamp = max(
            (row[7] for row in rows if row[7] is not None),
            default=None,
        )
        normalized_tenant_id = tenant_id.strip() if tenant_id and tenant_id.strip() else None
        source_window_trust = reconcile_cashflow_window(
            source_row_count=evidence.source_row_count,
            calculated_source_row_count=cashflow_count,
            output_group_count=len(buckets),
            source_component_totals=evidence.source_currency_totals,
            calculated_component_totals=calculated_currency_totals,
            latest_evidence_timestamp=latest_evidence_timestamp,
        )
        response_values = {
            "portfolio_id": portfolio_id,
            "start_date": start_date,
            "end_date": end_date,
            "portfolio_currency": portfolio_currency,
            "buckets": [bucket.model_dump(mode="python") for bucket in buckets],
            "cashflow_count": cashflow_count,
            "source_window_trust": source_window_trust.response.model_dump(mode="python"),
        }
        calculation_lineage = build_calculation_lineage(
            algorithm_id=CASH_MOVEMENT_ALGORITHM_ID,
            algorithm_version=CASH_MOVEMENT_ALGORITHM_VERSION,
            intermediate_precision=CASH_MOVEMENT_INTERMEDIATE_PRECISION,
            input_payload={
                "portfolio_id": portfolio_id,
                "tenant_id": normalized_tenant_id,
                "start_date": start_date,
                "end_date": end_date,
                "portfolio_currency": portfolio_currency,
                "source_rows": normalized_source_rows,
                "source_row_count": evidence.source_row_count,
                "source_currency_totals": evidence.source_currency_totals,
                "latest_evidence_timestamp": latest_evidence_timestamp,
            },
            output_payload=response_values,
        )
        request_fingerprint = (
            f"cash_movement_summary:{calculation_lineage.input_content_hash[:16]}"
        )
        content_hash = stable_content_hash(
            {
                "product_name": "PortfolioCashMovementSummary",
                "product_version": "v1",
                "tenant_id": normalized_tenant_id,
                "request_fingerprint": request_fingerprint,
                "response_values": response_values,
                "calculation_lineage": calculation_lineage.lineage_payload(),
                "latest_evidence_timestamp": latest_evidence_timestamp,
            }
        )

        return PortfolioCashMovementSummaryResponse(
            portfolio_id=portfolio_id,
            start_date=start_date,
            end_date=end_date,
            portfolio_currency=portfolio_currency,
            buckets=buckets,
            cashflow_count=cashflow_count,
            request_fingerprint=request_fingerprint,
            source_window_trust=source_window_trust.response,
            calculation_lineage=calculation_lineage.lineage_payload(),
            notes=(
                "Summary aggregates latest cashflow rows by classification, timing, currency, "
                "and flow scope. It is not a forecast, funding recommendation, treasury "
                "instruction, or OMS acknowledgement."
            ),
            **source_data_product_runtime_metadata(
                as_of_date=end_date,
                tenant_id=normalized_tenant_id,
                reconciliation_status=source_window_trust.reconciliation_status,
                data_quality_status=source_window_trust.data_quality_status,
                latest_evidence_timestamp=latest_evidence_timestamp,
                source_batch_fingerprint=(
                    f"cash_movement_summary:{portfolio_id}:{start_date}:{end_date}"
                ),
                snapshot_id=(
                    "cash_movement_summary:"
                    f"{calculation_lineage.output_content_hash[:24]}"
                ),
                policy_version=CASH_MOVEMENT_POLICY_VERSION,
                content_hash=content_hash,
                source_refs=[
                    "lotus-core://source/PortfolioCashMovementSummary/"
                    f"{portfolio_id}/{start_date.isoformat()}/{end_date.isoformat()}"
                ],
                lineage={
                    "source_owner": "lotus-core",
                    "source_product": "PortfolioCashMovementSummary",
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
    def _movement_direction(amount: Decimal) -> str:
        if amount > 0:
            return "INFLOW"
        if amount < 0:
            return "OUTFLOW"
        return "FLAT"
