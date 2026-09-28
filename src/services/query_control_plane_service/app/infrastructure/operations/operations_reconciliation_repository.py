"""Focused reconciliation evidence reads for operational support."""

from datetime import date, datetime
from typing import Optional

from portfolio_common.database_models import FinancialReconciliationRun
from portfolio_common.domain.tenant import TenantId
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.operations import ReconciliationRunEvidence
from .operations_reconciliation_run_queries import (
    apply_reconciliation_run_scope,
    reconciliation_run_priority,
)


class ReconciliationEvidenceRepositoryMixin:
    """Read tenant-scoped reconciliation evidence for a portfolio cut."""

    db: AsyncSession

    async def get_latest_reconciliation_run_for_portfolio_day(
        self,
        portfolio_id: str,
        business_date: date,
        epoch: int,
        *,
        tenant_id: TenantId,
        as_of: Optional[datetime] = None,
    ) -> ReconciliationRunEvidence | None:
        stmt = apply_reconciliation_run_scope(
            select(FinancialReconciliationRun),
            tenant_id=tenant_id,
            portfolio_id=portfolio_id,
            business_date=business_date,
            epoch=epoch,
            as_of=as_of,
            include_started_as_of=True,
        )
        stmt = stmt.order_by(
            reconciliation_run_priority(FinancialReconciliationRun.status).asc(),
            FinancialReconciliationRun.started_at.desc(),
            FinancialReconciliationRun.id.desc(),
        ).limit(1)
        row = (await self.db.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return ReconciliationRunEvidence(
            run_id=row.run_id,
            reconciliation_type=row.reconciliation_type,
            status=row.status,
            correlation_id=row.correlation_id,
            requested_by=row.requested_by,
            dedupe_key=row.dedupe_key,
            aggregation_revision=row.aggregation_revision,
            failure_reason=row.failure_reason,
        )


__all__ = ["ReconciliationEvidenceRepositoryMixin"]
