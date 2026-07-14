"""Verify SQLAlchemy corporate-action reconciliation persistence mapping."""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import Transaction as DBTransaction

from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    SqlAlchemyCorporateActionReconciliationRepository,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    CorporateActionReconciliationEvidence,
    CorporateActionReconciliationFindingEvidence,
    CorporateActionReconciliationKey,
    CorporateActionReconciliationRunEvidence,
)

pytestmark = pytest.mark.asyncio


async def test_load_group_maps_rows_to_domain_transactions() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyCorporateActionReconciliationRepository(db_session)
    row = DBTransaction(
        transaction_id="CA-OUT-01",
        portfolio_id="PORT_CA_01",
        instrument_id="AAPL",
        security_id="SEC_CA_01",
        transaction_type="DEMERGER_OUT",
        transaction_date=datetime(2026, 4, 10, 10, 0, tzinfo=UTC),
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=Decimal("100"),
        trade_currency="USD",
        currency="USD",
        linked_transaction_group_id="LTG-CA-01",
        parent_event_reference="CA-PARENT-01",
        dependency_reference_ids=["CA-IN-01"],
        net_cost_local=Decimal("-100"),
    )
    result = MagicMock()
    result.scalars.return_value.all.return_value = [row]
    db_session.execute.return_value = result
    key = CorporateActionReconciliationKey(
        portfolio_id="PORT_CA_01",
        linked_transaction_group_id="LTG-CA-01",
        parent_event_reference="CA-PARENT-01",
    )

    transactions = await repository.load_group(key)

    assert len(transactions) == 1
    assert transactions[0].transaction_id == "CA-OUT-01"
    assert transactions[0].dependency_reference_ids == ("CA-IN-01",)
    compiled_query = str(
        db_session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "transactions.portfolio_id = 'PORT_CA_01'" in compiled_query
    assert "transactions.linked_transaction_group_id = 'LTG-CA-01'" in compiled_query
    assert "transactions.parent_event_reference = 'CA-PARENT-01'" in compiled_query


async def test_save_evidence_maps_typed_records() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyCorporateActionReconciliationRepository(db_session)
    completed_at = datetime(2026, 4, 10, 12, 0, tzinfo=UTC)
    evidence = CorporateActionReconciliationEvidence(
        run=CorporateActionReconciliationRunEvidence(
            run_id="recon-ca-01",
            reconciliation_type="corporate_action_bundle_a",
            portfolio_id="PORT_CA_01",
            business_date=date(2026, 4, 10),
            epoch=9,
            status="COMPLETED",
            requested_by="cost-calculator",
            dedupe_key="auto:corporate_action_bundle_a:01",
            correlation_id="corr-ca-01",
            tolerance=Decimal("0.01"),
            summary={"passed": False},
            failure_reason=None,
            completed_at=completed_at,
        ),
        findings=(
            CorporateActionReconciliationFindingEvidence(
                finding_id="finding-ca-01",
                run_id="recon-ca-01",
                reconciliation_type="corporate_action_bundle_a",
                finding_type="ca_bundle_a_basis_mismatch",
                severity="ERROR",
                portfolio_id="PORT_CA_01",
                security_id="SEC_CA_01",
                transaction_id="CA-IN-01",
                business_date=date(2026, 4, 10),
                epoch=9,
                expected_value={"net_basis_delta_local_abs": "<= 0.01"},
                observed_value={"net_basis_delta_local": "-40"},
                detail={"reason_code": "CA_BUNDLE_A_BASIS_MISMATCH"},
            ),
        ),
    )

    await repository.save_evidence(evidence)

    assert db_session.execute.await_count == 2
    run_statement = db_session.execute.await_args_list[0].args[0]
    finding_statement = db_session.execute.await_args_list[1].args[0]
    assert run_statement.compile().params["run_id"] == "recon-ca-01"
    assert run_statement.compile().params["completed_at"] == completed_at
    assert finding_statement.compile().params["finding_id"] == "finding-ca-01"
    assert finding_statement.compile().params["severity"] == "ERROR"
