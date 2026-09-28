from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from portfolio_common.domain.tenant import TenantId
from pydantic import ValidationError

from src.services.financial_reconciliation_service.app.dtos import ReconciliationRunRequest
from src.services.financial_reconciliation_service.app.routers.reconciliation_mappers import (
    reconciliation_run_command_from_request,
    reconciliation_run_not_found,
    reconciliation_scope_not_found,
)


def test_reconciliation_run_command_from_request_preserves_api_context() -> None:
    command = reconciliation_run_command_from_request(
        ReconciliationRunRequest(
            portfolio_id="PF-1",
            business_date=date(2026, 3, 6),
            epoch=2,
            requested_by="ops",
            tolerance=Decimal("0.01"),
        ),
        tenant_id=TenantId("tenant-a"),
        correlation_id="corr-1",
    )

    assert command.portfolio_id == "PF-1"
    assert command.business_date == date(2026, 3, 6)
    assert command.epoch == 2
    assert command.requested_by == "ops"
    assert command.tolerance == Decimal("0.01")
    assert command.correlation_id == "corr-1"
    assert command.tenant_id == TenantId("tenant-a")


@pytest.mark.parametrize("tolerance", ["0.00000000001", "100000000"])
def test_reconciliation_request_rejects_unpersistable_tolerance(tolerance: str) -> None:
    with pytest.raises(ValidationError, match="reconciliation-tolerance-v1"):
        ReconciliationRunRequest(tolerance=Decimal(tolerance))


def test_reconciliation_request_accepts_exact_zero_tolerance() -> None:
    request = ReconciliationRunRequest(tolerance=Decimal("0.0000000000"))

    assert request.tolerance == Decimal("0.0000000000")


def test_reconciliation_run_not_found_maps_to_contract_detail() -> None:
    exc = reconciliation_run_not_found("RUN-404")

    assert isinstance(exc, HTTPException)
    assert exc.status_code == 404
    assert exc.detail == {
        "code": "RECONCILIATION_RUN_NOT_FOUND",
        "message": "Reconciliation run 'RUN-404' was not found.",
    }


def test_reconciliation_scope_not_found_does_not_disclose_portfolio_or_tenant() -> None:
    exc = reconciliation_scope_not_found()

    assert isinstance(exc, HTTPException)
    assert exc.status_code == 404
    assert exc.detail == {
        "code": "RECONCILIATION_SCOPE_NOT_FOUND",
        "message": "Requested reconciliation scope was not found.",
    }
