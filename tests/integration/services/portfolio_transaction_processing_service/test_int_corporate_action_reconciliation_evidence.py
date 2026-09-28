"""Persist tenant-fenced corporate-action reconciliation evidence exactly once."""

from dataclasses import asdict, replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    FinancialReconciliationFinding,
    FinancialReconciliationRun,
    Portfolio,
)
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.domain.tenant import TenantAuthorityMismatchError, TenantId
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
from src.services.portfolio_transaction_processing_service.app.ports import (
    CorporateActionReconciliationEvidence,
    CorporateActionReconciliationFindingEvidence,
    CorporateActionReconciliationKey,
)
from tests.test_support.transaction_processing import portfolio_record

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration_db,
    pytest.mark.db_direct,
    pytest.mark.regression,
]
TENANT_ID = TenantId("tenant-test")
FOREIGN_TENANT_ID = TenantId("tenant-other")


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


def _multi_defect_evidence() -> CorporateActionReconciliationEvidence:
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
    return build_corporate_action_reconciliation_evidence(
        tenant_id=TENANT_ID,
        processed_transaction=adjustment,
        input_transactions=transactions,
        linked_transaction_group_id="GROUP-CA-MULTI-DEFECT-01",
        parent_event_reference="PARENT-CA-MULTI-DEFECT-01",
        reconciliation=reconcile_corporate_action_basis(transactions),
        missing_dependency_reference_ids=(),
        correlation_id="corr-ca-multi-defect-01",
        completed_at=datetime(2026, 8, 11, 9, 1, tzinfo=UTC),
    )


def _portfolio(portfolio_id: str, *, tenant_id: TenantId) -> Portfolio:
    portfolio = portfolio_record(
        portfolio_id,
        client_id=f"CLIENT-{portfolio_id}",
    )
    portfolio.tenant_id = tenant_id.value
    return portfolio


def _run_record(
    evidence: CorporateActionReconciliationEvidence,
    *,
    tenant_id: TenantId,
) -> FinancialReconciliationRun:
    return FinancialReconciliationRun(
        **asdict(evidence.run),
        authority_scope="TENANT",
        tenant_id=tenant_id.value,
    )


def _finding_record(
    finding: CorporateActionReconciliationFindingEvidence,
    *,
    tenant_id: TenantId,
) -> FinancialReconciliationFinding:
    return FinancialReconciliationFinding(
        **asdict(finding),
        authority_scope="TENANT",
        tenant_id=tenant_id.value,
        created_at=datetime(2026, 8, 11, 8, 59, tzinfo=UTC),
    )


async def test_multi_defect_evidence_replay_preserves_one_run_and_exact_findings(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    async_db_session.add(portfolio_record("PORT-CA-MULTI-DEFECT-01"))
    await async_db_session.flush()
    evidence = _multi_defect_evidence()
    repository = SqlAlchemyCorporateActionReconciliationRepository(async_db_session)

    await repository.save_evidence(tenant_id=TENANT_ID, evidence=evidence)
    await repository.save_evidence(tenant_id=TENANT_ID, evidence=evidence)
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
    assert runs[0].tenant_id == TENANT_ID.value
    assert runs[0].summary["finding_count"] == len(findings) == 2
    assert runs[0].summary["error_count"] == len(findings)
    assert runs[0].summary["unsupported_adjustment_count"] == 1
    assert runs[0].summary["missing_cash_basis_count"] == 1
    assert {finding.finding_type for finding in findings} == {
        "ca_bundle_a_insufficient_cash_basis",
        "ca_bundle_a_unsupported_adjustment",
    }
    assert len({finding.finding_id for finding in findings}) == len(findings)
    assert {finding.tenant_id for finding in findings} == {TENANT_ID.value}


async def test_corporate_action_group_load_is_tenant_scoped(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-CA-TENANT-SCOPE-01"
    async_db_session.add(portfolio_record(portfolio_id))
    async_db_session.add(
        DBTransaction(
            transaction_id="CA-TENANT-SCOPE-OUT-01",
            portfolio_id=portfolio_id,
            instrument_id="SEC-CA-TENANT-SCOPE-01",
            security_id="SEC-CA-TENANT-SCOPE-01",
            transaction_type="DEMERGER_OUT",
            transaction_date=datetime(2026, 8, 11, 9, 0, tzinfo=UTC),
            quantity=Decimal(0),
            price=Decimal(0),
            gross_transaction_amount=Decimal("100"),
            trade_currency="USD",
            currency="USD",
            linked_transaction_group_id="GROUP-CA-TENANT-SCOPE-01",
            parent_event_reference="PARENT-CA-TENANT-SCOPE-01",
            net_cost_local=Decimal("-100"),
        )
    )
    await async_db_session.flush()
    repository = SqlAlchemyCorporateActionReconciliationRepository(async_db_session)

    owner_rows = await repository.load_group(
        CorporateActionReconciliationKey(
            tenant_id=TENANT_ID,
            portfolio_id=portfolio_id,
            linked_transaction_group_id="GROUP-CA-TENANT-SCOPE-01",
            parent_event_reference="PARENT-CA-TENANT-SCOPE-01",
        )
    )
    foreign_rows = await repository.load_group(
        CorporateActionReconciliationKey(
            tenant_id=TenantId("tenant-other"),
            portfolio_id=portfolio_id,
            linked_transaction_group_id="GROUP-CA-TENANT-SCOPE-01",
            parent_event_reference="PARENT-CA-TENANT-SCOPE-01",
        )
    )

    assert [row.transaction_id for row in owner_rows] == ["CA-TENANT-SCOPE-OUT-01"]
    assert foreign_rows == ()


async def test_foreign_run_identity_fails_before_zero_finding_resolution_side_effects(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    evidence = _multi_defect_evidence()
    foreign_run_id = "recon-ca-foreign-run-collision"
    owner_prior_run_id = "recon-ca-owner-prior-run"
    foreign_evidence = replace(
        evidence,
        tenant_id=FOREIGN_TENANT_ID,
        run=replace(
            evidence.run,
            run_id=foreign_run_id,
            portfolio_id="PORT-CA-FOREIGN",
            dedupe_key="auto:corporate-action:foreign-run",
        ),
        findings=(),
    )
    owner_prior_evidence = replace(
        evidence,
        run=replace(
            evidence.run,
            run_id=owner_prior_run_id,
            dedupe_key="auto:corporate-action:owner-prior-run",
        ),
    )
    owner_prior_finding = replace(
        owner_prior_evidence.findings[0],
        finding_id="finding-ca-owner-prior-run",
        run_id=owner_prior_run_id,
    )
    async_db_session.add_all(
        [
            _portfolio("PORT-CA-MULTI-DEFECT-01", tenant_id=TENANT_ID),
            _portfolio("PORT-CA-FOREIGN", tenant_id=FOREIGN_TENANT_ID),
        ]
    )
    await async_db_session.flush()
    async_db_session.add_all(
        [
            _run_record(foreign_evidence, tenant_id=FOREIGN_TENANT_ID),
            _run_record(owner_prior_evidence, tenant_id=TENANT_ID),
        ]
    )
    await async_db_session.flush()
    async_db_session.add(_finding_record(owner_prior_finding, tenant_id=TENANT_ID))
    await async_db_session.commit()

    incoming = replace(
        evidence,
        run=replace(
            evidence.run,
            run_id=foreign_run_id,
            dedupe_key="auto:corporate-action:owner-colliding-run",
        ),
        findings=(),
    )
    repository = SqlAlchemyCorporateActionReconciliationRepository(async_db_session)
    with pytest.raises(TenantAuthorityMismatchError, match="run identity"):
        async with async_db_session.begin():
            await repository.save_evidence(tenant_id=TENANT_ID, evidence=incoming)

    owner_collision = (
        await async_db_session.execute(
            select(FinancialReconciliationRun).where(
                FinancialReconciliationRun.run_id == foreign_run_id,
                FinancialReconciliationRun.tenant_id == TENANT_ID.value,
            )
        )
    ).scalar_one_or_none()
    prior_finding = (
        await async_db_session.execute(
            select(FinancialReconciliationFinding).where(
                FinancialReconciliationFinding.finding_id == owner_prior_finding.finding_id
            )
        )
    ).scalar_one()
    assert owner_collision is None
    assert prior_finding.resolution_state == "OPEN"
    assert prior_finding.resolution_actor is None
    assert prior_finding.resolved_at is None


async def test_foreign_finding_identity_rolls_back_run_and_resolution_side_effects(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    evidence = _multi_defect_evidence()
    foreign_run_id = "recon-ca-foreign-finding-run"
    foreign_finding_id = "finding-ca-foreign-collision"
    owner_prior_run_id = "recon-ca-owner-prior-finding-run"
    owner_incoming_run_id = "recon-ca-owner-incoming-run"
    foreign_evidence = replace(
        evidence,
        tenant_id=FOREIGN_TENANT_ID,
        run=replace(
            evidence.run,
            run_id=foreign_run_id,
            portfolio_id="PORT-CA-FOREIGN",
            dedupe_key="auto:corporate-action:foreign-finding-run",
        ),
    )
    foreign_finding = replace(
        foreign_evidence.findings[0],
        finding_id=foreign_finding_id,
        run_id=foreign_run_id,
        portfolio_id="PORT-CA-FOREIGN",
    )
    owner_prior_evidence = replace(
        evidence,
        run=replace(
            evidence.run,
            run_id=owner_prior_run_id,
            dedupe_key="auto:corporate-action:owner-prior-finding-run",
        ),
    )
    owner_prior_finding = replace(
        owner_prior_evidence.findings[0],
        finding_id="finding-ca-owner-before-collision",
        run_id=owner_prior_run_id,
    )
    async_db_session.add_all(
        [
            _portfolio("PORT-CA-MULTI-DEFECT-01", tenant_id=TENANT_ID),
            _portfolio("PORT-CA-FOREIGN", tenant_id=FOREIGN_TENANT_ID),
        ]
    )
    await async_db_session.flush()
    async_db_session.add_all(
        [
            _run_record(foreign_evidence, tenant_id=FOREIGN_TENANT_ID),
            _run_record(owner_prior_evidence, tenant_id=TENANT_ID),
        ]
    )
    await async_db_session.flush()
    async_db_session.add_all(
        [
            _finding_record(foreign_finding, tenant_id=FOREIGN_TENANT_ID),
            _finding_record(owner_prior_finding, tenant_id=TENANT_ID),
        ]
    )
    await async_db_session.commit()

    incoming = replace(
        evidence,
        run=replace(
            evidence.run,
            run_id=owner_incoming_run_id,
            dedupe_key="auto:corporate-action:owner-incoming-run",
        ),
        findings=(
            replace(
                evidence.findings[0],
                finding_id=foreign_finding_id,
                run_id=owner_incoming_run_id,
            ),
        ),
    )
    repository = SqlAlchemyCorporateActionReconciliationRepository(async_db_session)
    with pytest.raises(TenantAuthorityMismatchError, match="finding identity"):
        async with async_db_session.begin():
            await repository.save_evidence(tenant_id=TENANT_ID, evidence=incoming)

    incoming_run = (
        await async_db_session.execute(
            select(FinancialReconciliationRun).where(
                FinancialReconciliationRun.run_id == owner_incoming_run_id
            )
        )
    ).scalar_one_or_none()
    prior_finding = (
        await async_db_session.execute(
            select(FinancialReconciliationFinding).where(
                FinancialReconciliationFinding.finding_id == owner_prior_finding.finding_id
            )
        )
    ).scalar_one()
    persisted_foreign_finding = (
        await async_db_session.execute(
            select(FinancialReconciliationFinding).where(
                FinancialReconciliationFinding.finding_id == foreign_finding_id
            )
        )
    ).scalar_one()
    assert incoming_run is None
    assert prior_finding.resolution_state == "OPEN"
    assert prior_finding.resolution_actor is None
    assert prior_finding.resolved_at is None
    assert persisted_foreign_finding.tenant_id == FOREIGN_TENANT_ID.value
    assert persisted_foreign_finding.run_id == foreign_run_id
