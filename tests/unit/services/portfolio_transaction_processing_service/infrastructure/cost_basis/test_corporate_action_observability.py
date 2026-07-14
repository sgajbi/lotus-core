"""Tests for corporate-action reconciliation telemetry adaptation."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    PrometheusCorporateActionReconciliationObserver,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    CorporateActionReconciliationKey,
    CorporateActionReconciliationObservation,
)


def _observation(
    *,
    status: str = "balanced",
    missing_cash_basis_count: int = 0,
    missing_dependencies: tuple[str, ...] = (),
    finding_severities: tuple[str, ...] = (),
) -> CorporateActionReconciliationObservation:
    transaction = BookedTransaction(
        transaction_id="CA-IN-01",
        portfolio_id="PORT_CA_01",
        instrument_id="AAPL",
        security_id="SEC_CA_01",
        transaction_date=datetime(2026, 4, 10, tzinfo=UTC),
        transaction_type="DEMERGER_IN",
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=Decimal("100"),
        trade_currency="USD",
        currency="USD",
    )
    return CorporateActionReconciliationObservation(
        key=CorporateActionReconciliationKey(
            portfolio_id="PORT_CA_01",
            linked_transaction_group_id="LTG-CA-01",
            parent_event_reference="CA-PARENT-01",
        ),
        processed_transaction=transaction,
        reconciliation_status=status,
        source_leg_count=1,
        target_leg_count=1,
        cash_consideration_count=1 if missing_cash_basis_count else 0,
        source_basis_out_local=Decimal("100"),
        target_basis_in_local=Decimal("60") if status == "basis_mismatch" else Decimal("100"),
        cash_basis_local=Decimal("0"),
        missing_cash_basis_count=missing_cash_basis_count,
        net_basis_delta_local=Decimal("-40") if status == "basis_mismatch" else Decimal("0"),
        basis_tolerance=Decimal("0.01"),
        missing_dependency_reference_ids=missing_dependencies,
        finding_severities=finding_severities,
    )


def test_observer_preserves_metric_and_balanced_state_log_contract() -> None:
    observation = _observation()

    with (
        patch(
            "src.services.portfolio_transaction_processing_service.app.infrastructure."
            "cost_basis.corporate_action_observability."
            "observe_financial_reconciliation_run"
        ) as observe_run,
        patch(
            "src.services.portfolio_transaction_processing_service.app.infrastructure."
            "cost_basis.corporate_action_observability.logger"
        ) as logger,
    ):
        PrometheusCorporateActionReconciliationObserver().observe(observation)

    observe_run.assert_called_once()
    reconciliation_type, status, duration, findings = observe_run.call_args.args
    assert reconciliation_type == "corporate_action_bundle_a"
    assert status == "COMPLETED"
    assert duration == 0.0
    assert findings == ()
    logger.info.assert_called_once_with(
        "bundle_a_reconciliation_state",
        extra={
            "portfolio_id": "PORT_CA_01",
            "transaction_id": "CA-IN-01",
            "linked_transaction_group_id": "LTG-CA-01",
            "parent_event_reference": "CA-PARENT-01",
            "reconciliation_status": "balanced",
            "source_leg_count": 1,
            "target_leg_count": 1,
            "cash_consideration_count": 0,
            "source_basis_out_local": "100",
            "target_basis_in_local": "100",
            "cash_basis_local": "0",
            "missing_cash_basis_count": 0,
            "net_basis_delta_local": "0",
            "basis_tolerance": "0.01",
            "missing_dependency_reference_ids": [],
        },
    )
    logger.warning.assert_not_called()


def test_observer_emits_each_actionable_support_warning() -> None:
    observation = _observation(
        status="basis_mismatch",
        missing_dependencies=("CA-OUT-MISSING",),
        finding_severities=("ERROR", "ERROR"),
    )

    with (
        patch(
            "src.services.portfolio_transaction_processing_service.app.infrastructure."
            "cost_basis.corporate_action_observability."
            "observe_financial_reconciliation_run"
        ) as observe_run,
        patch(
            "src.services.portfolio_transaction_processing_service.app.infrastructure."
            "cost_basis.corporate_action_observability.logger"
        ) as logger,
    ):
        PrometheusCorporateActionReconciliationObserver().observe(observation)

    findings = observe_run.call_args.args[3]
    assert tuple(finding.severity for finding in findings) == ("ERROR", "ERROR")
    assert [call.args[0] for call in logger.warning.call_args_list] == [
        "bundle_a_basis_mismatch_detected",
        "bundle_a_dependency_gap_detected",
    ]


def test_observer_reports_missing_cash_basis() -> None:
    observation = _observation(
        status="insufficient_cash_basis",
        missing_cash_basis_count=1,
        finding_severities=("ERROR",),
    )

    with (
        patch(
            "src.services.portfolio_transaction_processing_service.app.infrastructure."
            "cost_basis.corporate_action_observability."
            "observe_financial_reconciliation_run"
        ),
        patch(
            "src.services.portfolio_transaction_processing_service.app.infrastructure."
            "cost_basis.corporate_action_observability.logger"
        ) as logger,
    ):
        PrometheusCorporateActionReconciliationObserver().observe(observation)

    logger.warning.assert_called_once()
    assert logger.warning.call_args.args[0] == "bundle_a_cash_basis_evidence_missing"


def test_observer_contains_telemetry_failure_after_financial_persistence() -> None:
    """Telemetry must not roll back already-computed reconciliation evidence."""

    observation = _observation()

    with (
        patch(
            "src.services.portfolio_transaction_processing_service.app.infrastructure."
            "cost_basis.corporate_action_observability."
            "observe_financial_reconciliation_run",
            side_effect=RuntimeError("metrics unavailable"),
        ),
        patch(
            "src.services.portfolio_transaction_processing_service.app.infrastructure."
            "cost_basis.corporate_action_observability.logger"
        ) as logger,
    ):
        PrometheusCorporateActionReconciliationObserver().observe(observation)

    logger.exception.assert_called_once_with(
        "Corporate-action reconciliation observation failed.",
        extra={
            "portfolio_id": "PORT_CA_01",
            "transaction_id": "CA-IN-01",
            "reconciliation_status": "balanced",
        },
    )
