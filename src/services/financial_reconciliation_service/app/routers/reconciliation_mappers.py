from __future__ import annotations

from fastapi import HTTPException
from portfolio_common.domain.tenant import TenantId

from ..application import ReconciliationRunCommand
from ..dtos import ReconciliationRunRequest


def reconciliation_run_command_from_request(
    request: ReconciliationRunRequest,
    *,
    tenant_id: TenantId,
    correlation_id: str | None,
) -> ReconciliationRunCommand:
    return ReconciliationRunCommand(
        tenant_id=tenant_id,
        portfolio_id=request.portfolio_id,
        business_date=request.business_date,
        epoch=request.epoch,
        requested_by=request.requested_by,
        tolerance=request.tolerance,
        correlation_id=correlation_id,
    )


def reconciliation_scope_not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": "RECONCILIATION_SCOPE_NOT_FOUND",
            "message": "Requested reconciliation scope was not found.",
        },
    )


def reconciliation_run_not_found(run_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": "RECONCILIATION_RUN_NOT_FOUND",
            "message": f"Reconciliation run '{run_id}' was not found.",
        },
    )
