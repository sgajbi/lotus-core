"""Tenant-aware portfolio authority helpers for operational support."""

from datetime import date, datetime
from typing import cast

from portfolio_common.domain.tenant import TenantId

from ...domain.operations import (
    PortfolioControlStageEvidence,
    ReconciliationFindingSummary,
    ReconciliationRunEvidence,
)
from ...ports.operations import OperationsSupportRepository


class PortfolioAuthorityServiceMixin:
    """Resolve portfolio authority without disclosing foreign scope existence."""

    repo: OperationsSupportRepository

    async def _ensure_portfolio_exists(
        self,
        portfolio_id: str,
        *,
        tenant_id: TenantId | None = None,
    ) -> None:
        exists = (
            await self.repo.portfolio_exists(portfolio_id)
            if tenant_id is None
            else await self.repo.portfolio_exists_for_tenant(portfolio_id, tenant_id=tenant_id)
        )
        if not exists:
            message = (
                f"Portfolio with id {portfolio_id} not found"
                if tenant_id is None
                else "Requested operations support resource was not found"
            )
            raise ValueError(message)

    async def _resolve_portfolio_latest_business_date(
        self,
        portfolio_id: str,
        *,
        tenant_id: TenantId | None = None,
        generated_at_utc: datetime,
    ) -> date | None:
        await self._ensure_portfolio_exists(portfolio_id, tenant_id=tenant_id)
        return cast(
            date | None,
            await self.repo.get_latest_business_date(as_of=generated_at_utc),
        )

    async def _read_latest_reconciliation_evidence(
        self,
        *,
        tenant_id: TenantId,
        portfolio_id: str,
        latest_control_stage: PortfolioControlStageEvidence | None,
    ) -> tuple[ReconciliationRunEvidence | None, ReconciliationFindingSummary | None]:
        if latest_control_stage is None:
            return None, None

        latest_run = await self.repo.get_latest_reconciliation_run_for_portfolio_day(
            portfolio_id=portfolio_id,
            business_date=latest_control_stage.business_date,
            epoch=latest_control_stage.epoch,
            tenant_id=tenant_id,
            as_of=latest_control_stage.updated_at,
        )
        if latest_run is None:
            return None, None

        finding_summary = await self.repo.get_reconciliation_finding_summary(
            latest_run.run_id,
            tenant_id=tenant_id,
            as_of=latest_control_stage.updated_at,
        )
        return latest_run, finding_summary


__all__ = ["PortfolioAuthorityServiceMixin"]
