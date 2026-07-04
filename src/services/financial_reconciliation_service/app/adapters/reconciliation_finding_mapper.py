from portfolio_common.database_models import FinancialReconciliationFinding

from ..domain.reconciliation_policies import ReconciliationFinding


def reconciliation_finding_to_orm(
    finding: ReconciliationFinding,
    *,
    run_id: str,
    finding_id: str,
) -> FinancialReconciliationFinding:
    return FinancialReconciliationFinding(
        finding_id=finding_id,
        run_id=run_id,
        reconciliation_type=finding.reconciliation_type,
        finding_type=finding.finding_type,
        severity=finding.severity,
        portfolio_id=finding.portfolio_id,
        security_id=finding.security_id,
        transaction_id=finding.transaction_id,
        business_date=finding.business_date,
        epoch=finding.epoch,
        expected_value=finding.expected_value,
        observed_value=finding.observed_value,
        detail=finding.detail,
    )
