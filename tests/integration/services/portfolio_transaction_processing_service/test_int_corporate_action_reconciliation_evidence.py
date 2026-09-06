"""Persist multi-defect corporate-action reconciliation evidence exactly once."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    FinancialReconciliationFinding,
    FinancialReconciliationRun,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.application import (
    build_corporate_action_reconciliation_evidence,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    reconcile_corporate_action_basis,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    SqlAlchemyCorporateActionReconciliationRepository,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration_db,
    pytest.mark.db_direct,
    pytest.mark.regression,
]


def _transaction(
    *,
    transaction_id: str,
    transaction_type: str,
    net_cost_local: str,
) -> BookedTransaction:
    return BookedTransaction(
        transaction_id=transaction_id,
        portfolio_id="PORT-CA-MULTI-DEFECT-01",
        tenant_id="tenant-test",
        instrument_id="SEC-CA-MULTI-DEFECT-01",
        security_id="SEC-CA-MULTI-DEFECT-01",
        transaction_date=datetime(2026, 8, 11, 9, 0, tzinfo=UTC),
        transaction_type=transaction_type,
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=abs(Decimal(net_cost_local)),
        trade_currency="USD",
        currency="USD",
        linked_transaction_group_id="GROUP-CA-MULTI-DEFECT-01",
        parent_event_reference="PARENT-CA-MULTI-DEFECT-01",
        net_cost_local=Decimal(net_cost_local),
        epoch=3,
    )


async def test_multi_defect_evidence_replay_preserves_one_run_and_exact_findings(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    source = _transaction(
        transaction_id="CA-OUT-MULTI-DEFECT-01",
        transaction_type="SPIN_OFF",
        net_cost_local="-100",
    )
    target = _transaction(
        transaction_id="CA-IN-MULTI-DEFECT-01",
        transaction_type="SPIN_IN",
        net_cost_local="100",
    )
    cash = _transaction(
        transaction_id="CA-CASH-MULTI-DEFECT-01",
        transaction_type="CASH_CONSIDERATION",
        net_cost_local="0",
    )
    adjustment = replace(
        _transaction(
            transaction_id="CA-ADJ-MULTI-DEFECT-01",
            transaction_type="ADJUSTMENT",
            net_cost_local="5",
        ),
        adjustment_reason="MANUAL_BASIS_OVERRIDE",
        movement_direction="INFLOW",
    )
    transactions = (source, target, cash, adjustment)
    reconciliation = reconcile_corporate_action_basis(transactions)
    evidence = build_corporate_action_reconciliation_evidence(
        processed_transaction=adjustment,
        input_transactions=transactions,
        linked_transaction_group_id="GROUP-CA-MULTI-DEFECT-01",
        parent_event_reference="PARENT-CA-MULTI-DEFECT-01",
        reconciliation=reconciliation,
        missing_dependency_reference_ids=(),
        correlation_id="corr-ca-multi-defect-01",
        completed_at=datetime(2026, 8, 11, 9, 1, tzinfo=UTC),
    )
    repository = SqlAlchemyCorporateActionReconciliationRepository(async_db_session)

    await repository.save_evidence(evidence)
    await repository.save_evidence(evidence)
    await async_db_session.commit()

    runs = (
        (
            await async_db_session.execute(
                select(FinancialReconciliationRun).where(
                    FinancialReconciliationRun.run_id == evidence.run.run_id
                )
            )
        )
        .scalars()
        .all()
    )
    findings = (
        (
            await async_db_session.execute(
                select(FinancialReconciliationFinding).where(
                    FinancialReconciliationFinding.run_id == evidence.run.run_id
                )
            )
        )
        .scalars()
        .all()
    )

    assert len(runs) == 1
    assert runs[0].summary["finding_count"] == len(findings) == 2
    assert runs[0].summary["error_count"] == len(findings)
    assert runs[0].summary["unsupported_adjustment_count"] == 1
    assert runs[0].summary["missing_cash_basis_count"] == 1
    assert {finding.finding_type for finding in findings} == {
        "ca_bundle_a_insufficient_cash_basis",
        "ca_bundle_a_unsupported_adjustment",
    }
    assert len({finding.finding_id for finding in findings}) == len(findings)
