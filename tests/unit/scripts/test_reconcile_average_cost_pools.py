from decimal import Decimal

from scripts.reconcile_average_cost_pools import SCHEMA_VERSION, build_report, exit_code
from src.services.portfolio_transaction_processing_service.app.application import (
    ReconcileAverageCostPoolsResult,
)
from src.services.portfolio_transaction_processing_service.app.domain import (
    AverageCostPoolKey,
    AverageCostPoolReconciliationAssessment,
    AverageCostPoolReconciliationStatus,
)


def _assessment(
    status: AverageCostPoolReconciliationStatus,
    *,
    reason_code: str | None = None,
) -> AverageCostPoolReconciliationAssessment:
    key = AverageCostPoolKey("P1", "S1")
    pool_quantity = (
        Decimal("9") if status is AverageCostPoolReconciliationStatus.DRIFTED else Decimal("10")
    )
    return AverageCostPoolReconciliationAssessment(
        key=key,
        status=status,
        expected_source_count=1,
        expected_quantity=Decimal("10"),
        expected_cost_local=Decimal("100"),
        expected_cost_base=Decimal("120"),
        source_count=1,
        pool_quantity=pool_quantity,
        pool_cost_local=Decimal("100"),
        pool_cost_base=Decimal("120"),
        source_quantity=Decimal("10"),
        source_cost_local=Decimal("100"),
        source_cost_base=Decimal("120"),
        reason_code=reason_code,
    )


def test_report_is_decimal_safe_and_exposes_resume_cursor() -> None:
    result = ReconcileAverageCostPoolsResult(
        apply=True,
        assessments=(_assessment(AverageCostPoolReconciliationStatus.RECONCILED),),
        next_cursor=AverageCostPoolKey("P1", "S1"),
    )

    report = build_report(result)

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["mode"] == "apply"
    assert report["summary"] == {
        "candidate_count": 1,
        "current_count": 0,
        "drifted_count": 0,
        "reconciled_count": 1,
        "failed_count": 0,
    }
    assert report["next_cursor"] == {"portfolio_id": "P1", "security_id": "S1"}
    assert report["assessments"][0]["expected_quantity"] == "10"
    assert report["assessments"][0]["status"] == "reconciled"
    assert exit_code(report) == 0


def test_dry_run_drift_and_failure_use_distinct_nonzero_exit_codes() -> None:
    drift = build_report(
        ReconcileAverageCostPoolsResult(
            apply=False,
            assessments=(
                _assessment(
                    AverageCostPoolReconciliationStatus.DRIFTED,
                    reason_code="pool_or_source_aggregate_mismatch",
                ),
            ),
            next_cursor=None,
        )
    )
    failure_assessment = _assessment(
        AverageCostPoolReconciliationStatus.FAILED,
        reason_code="average_cost_reconciliation_failed",
    )
    failure = build_report(
        ReconcileAverageCostPoolsResult(
            apply=True,
            assessments=(failure_assessment,),
            next_cursor=None,
        )
    )

    assert exit_code(drift) == 1
    assert exit_code(failure) == 2
