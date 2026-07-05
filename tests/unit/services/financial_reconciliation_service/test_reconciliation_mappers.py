from datetime import date
from decimal import Decimal

from fastapi import HTTPException

from src.services.financial_reconciliation_service.app.dtos import ReconciliationRunRequest
from src.services.financial_reconciliation_service.app.routers.reconciliation_mappers import (
    reconciliation_run_command_from_request,
    reconciliation_run_not_found,
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
        correlation_id="corr-1",
    )

    assert command.portfolio_id == "PF-1"
    assert command.business_date == date(2026, 3, 6)
    assert command.epoch == 2
    assert command.requested_by == "ops"
    assert command.tolerance == Decimal("0.01")
    assert command.correlation_id == "corr-1"


def test_reconciliation_run_not_found_maps_to_contract_detail() -> None:
    exc = reconciliation_run_not_found("RUN-404")

    assert isinstance(exc, HTTPException)
    assert exc.status_code == 404
    assert exc.detail == {
        "code": "RECONCILIATION_RUN_NOT_FOUND",
        "message": "Reconciliation run 'RUN-404' was not found.",
    }
