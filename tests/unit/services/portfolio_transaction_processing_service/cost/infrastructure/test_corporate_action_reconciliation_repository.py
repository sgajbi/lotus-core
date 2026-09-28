"""Verify SQLAlchemy corporate-action reconciliation persistence mapping."""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.domain.tenant import TenantAuthorityMismatchError, TenantId

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
TENANT_ID = TenantId("tenant-test")


def _statement_result(returned_identity: str | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = returned_identity
    return result


def _evidence(
    *,
    run_id: str = "recon-ca-collision",
    finding_id: str | None = "finding-ca-collision",
) -> CorporateActionReconciliationEvidence:
    findings = ()
    if finding_id is not None:
        findings = (
            CorporateActionReconciliationFindingEvidence(
                finding_id=finding_id,
                run_id=run_id,
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
                owner="CORPORATE_ACTION_OPERATIONS",
                resolution_state="OPEN",
                tolerance=Decimal("0.01"),
                observed_delta=Decimal("-40"),
                repair_recommendation="REVIEW_CORPORATE_ACTION_BASIS_ALLOCATION",
            ),
        )
    return CorporateActionReconciliationEvidence(
        tenant_id=TENANT_ID,
        run=CorporateActionReconciliationRunEvidence(
            run_id=run_id,
            reconciliation_type="corporate_action_bundle_a",
            portfolio_id="PORT_CA_01",
            business_date=date(2026, 4, 10),
            epoch=9,
            status="COMPLETED",
            requested_by="cost-calculator",
            dedupe_key=f"auto:corporate_action_bundle_a:{run_id}",
            correlation_id="corr-ca-collision",
            tolerance=Decimal("0.01"),
            summary={
                "passed": finding_id is None,
                "linked_transaction_group_id": "LTG-CA-01",
                "parent_event_reference": "CA-PARENT-01",
            },
            failure_reason=None,
            completed_at=datetime(2026, 4, 10, 12, 0, tzinfo=UTC),
        ),
        findings=findings,
    )


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
        tenant_id=TENANT_ID,
        portfolio_id="PORT_CA_01",
        linked_transaction_group_id="LTG-CA-01",
        parent_event_reference="CA-PARENT-01",
    )

    transactions = await repository.load_group(key)

    assert len(transactions) == 1
    assert transactions[0].transaction_id == "CA-OUT-01"
    assert transactions[0].tenant_id == TENANT_ID.value
    assert transactions[0].dependency_reference_ids == ("CA-IN-01",)
    compiled_query = str(
        db_session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "transactions.portfolio_id = 'PORT_CA_01'" in compiled_query
    assert "portfolios.tenant_id = 'tenant-test'" in compiled_query
    assert compiled_query.index("portfolios.tenant_id = 'tenant-test'") < compiled_query.index(
        "transactions.portfolio_id = 'PORT_CA_01'"
    )
    assert "transactions.linked_transaction_group_id = 'LTG-CA-01'" in compiled_query
    assert "transactions.parent_event_reference = 'CA-PARENT-01'" in compiled_query
    assert "'EXCHANGE_OUT'" in compiled_query
    assert "'EXCHANGE_IN'" in compiled_query
    assert "'CASH_IN_LIEU'" in compiled_query
    assert "'ADJUSTMENT'" in compiled_query


async def test_save_evidence_maps_typed_records() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyCorporateActionReconciliationRepository(db_session)
    completed_at = datetime(2026, 4, 10, 12, 0, tzinfo=UTC)
    evidence = CorporateActionReconciliationEvidence(
        tenant_id=TENANT_ID,
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
            summary={
                "passed": False,
                "linked_transaction_group_id": "LTG-CA-01",
                "parent_event_reference": "CA-PARENT-01",
            },
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
                owner="CORPORATE_ACTION_OPERATIONS",
                resolution_state="OPEN",
                tolerance=Decimal("0.01"),
                observed_delta=Decimal("-40"),
                repair_recommendation="REVIEW_CORPORATE_ACTION_BASIS_ALLOCATION",
            ),
        ),
    )
    db_session.execute.side_effect = [
        _statement_result("recon-ca-01"),
        MagicMock(),
        _statement_result("finding-ca-01"),
    ]

    await repository.save_evidence(tenant_id=TENANT_ID, evidence=evidence)

    assert db_session.execute.await_count == 3
    run_statement = db_session.execute.await_args_list[0].args[0]
    resolution_statement = db_session.execute.await_args_list[1].args[0]
    finding_statement = db_session.execute.await_args_list[2].args[0]
    assert run_statement.compile().params["run_id"] == "recon-ca-01"
    assert run_statement.compile().params["authority_scope"] == "TENANT"
    assert run_statement.compile().params["tenant_id"] == "tenant-test"
    assert run_statement.compile().params["completed_at"] == completed_at
    compiled_run = run_statement.compile()
    assert "financial_reconciliation_runs.authority_scope =" in str(compiled_run)
    assert "financial_reconciliation_runs.tenant_id =" in str(compiled_run)
    assert compiled_run.params["authority_scope_1"] == "TENANT"
    assert compiled_run.params["tenant_id_1"] == "tenant-test"
    assert "RETURNING financial_reconciliation_runs.run_id" in str(compiled_run)
    compiled_resolution = str(resolution_statement.compile(compile_kwargs={"literal_binds": True}))
    assert "resolution_state='RESOLVED'" in compiled_resolution.replace(" ", "")
    assert "financial_reconciliation_findings.tenant_id = 'tenant-test'" in compiled_resolution
    assert compiled_resolution.index("financial_reconciliation_findings.tenant_id") < (
        compiled_resolution.index("financial_reconciliation_findings.reconciliation_type")
    )
    assert "LTG-CA-01" in compiled_resolution
    assert "CA-PARENT-01" in compiled_resolution
    assert finding_statement.compile().params["finding_id"] == "finding-ca-01"
    assert finding_statement.compile().params["authority_scope"] == "TENANT"
    assert finding_statement.compile().params["tenant_id"] == "tenant-test"
    compiled_finding = finding_statement.compile()
    assert "financial_reconciliation_findings.authority_scope =" in str(compiled_finding)
    assert "financial_reconciliation_findings.tenant_id =" in str(compiled_finding)
    assert compiled_finding.params["authority_scope_1"] == "TENANT"
    assert compiled_finding.params["tenant_id_1"] == "tenant-test"
    assert "RETURNING financial_reconciliation_findings.finding_id" in str(compiled_finding)
    assert finding_statement.compile().params["severity"] == "ERROR"
    assert finding_statement.compile().params["owner"] == "CORPORATE_ACTION_OPERATIONS"
    assert finding_statement.compile().params["resolution_state"] == "OPEN"
    assert finding_statement.compile().params["tolerance"] == Decimal("0.01")
    assert finding_statement.compile().params["observed_delta"] == Decimal("-40")


async def test_save_evidence_rejects_missing_group_identity() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyCorporateActionReconciliationRepository(db_session)
    completed_at = datetime(2026, 4, 10, 12, 0, tzinfo=UTC)
    evidence = CorporateActionReconciliationEvidence(
        tenant_id=TENANT_ID,
        run=CorporateActionReconciliationRunEvidence(
            run_id="recon-ca-invalid",
            reconciliation_type="corporate_action_bundle_a",
            portfolio_id="PORT_CA_01",
            business_date=date(2026, 4, 10),
            epoch=9,
            status="COMPLETED",
            requested_by="cost-calculator",
            dedupe_key="auto:corporate_action_bundle_a:invalid",
            correlation_id=None,
            tolerance=Decimal("0.01"),
            summary={"passed": True},
            failure_reason=None,
            completed_at=completed_at,
        ),
        findings=(),
    )
    db_session.execute.return_value = _statement_result("recon-ca-invalid")

    with pytest.raises(ValueError, match="linked_transaction_group_id"):
        await repository.save_evidence(tenant_id=TENANT_ID, evidence=evidence)


async def test_save_evidence_rejects_cross_tenant_authority_before_writes() -> None:
    db_session = AsyncMock()
    repository = SqlAlchemyCorporateActionReconciliationRepository(db_session)
    evidence = CorporateActionReconciliationEvidence(
        tenant_id=TENANT_ID,
        run=CorporateActionReconciliationRunEvidence(
            run_id="recon-ca-cross-tenant",
            reconciliation_type="corporate_action_bundle_a",
            portfolio_id="PORT_CA_01",
            business_date=date(2026, 4, 10),
            epoch=9,
            status="COMPLETED",
            requested_by="cost-calculator",
            dedupe_key="auto:corporate_action_bundle_a:cross-tenant",
            correlation_id=None,
            tolerance=Decimal("0.01"),
            summary={
                "linked_transaction_group_id": "LTG-CA-01",
                "parent_event_reference": "CA-PARENT-01",
            },
            failure_reason=None,
            completed_at=datetime(2026, 4, 10, 12, 0, tzinfo=UTC),
        ),
        findings=(),
    )

    with pytest.raises(TenantAuthorityMismatchError, match="does not match admitted"):
        await repository.save_evidence(
            tenant_id=TenantId("tenant-other"),
            evidence=evidence,
        )

    db_session.execute.assert_not_awaited()


async def test_save_evidence_rejects_foreign_run_identity_before_resolution() -> None:
    db_session = AsyncMock()
    db_session.execute.return_value = _statement_result(None)
    repository = SqlAlchemyCorporateActionReconciliationRepository(db_session)

    with pytest.raises(TenantAuthorityMismatchError, match="run identity"):
        await repository.save_evidence(
            tenant_id=TENANT_ID,
            evidence=_evidence(finding_id=None),
        )

    assert db_session.execute.await_count == 1


async def test_save_evidence_rejects_foreign_finding_identity_after_fenced_run() -> None:
    db_session = AsyncMock()
    db_session.execute.side_effect = [
        _statement_result("recon-ca-collision"),
        MagicMock(),
        _statement_result(None),
    ]
    repository = SqlAlchemyCorporateActionReconciliationRepository(db_session)

    with pytest.raises(TenantAuthorityMismatchError, match="finding identity"):
        await repository.save_evidence(
            tenant_id=TENANT_ID,
            evidence=_evidence(),
        )

    assert db_session.execute.await_count == 3
