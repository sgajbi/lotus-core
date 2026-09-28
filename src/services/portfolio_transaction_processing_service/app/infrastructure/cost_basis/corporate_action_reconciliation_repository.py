"""SQLAlchemy adapter for corporate-action cost-basis reconciliation evidence."""

from dataclasses import asdict, replace

from portfolio_common.database_models import (
    FinancialReconciliationFinding,
    FinancialReconciliationRun,
    Portfolio,
)
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.domain.tenant import TenantAuthorityMismatchError, TenantId
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain import BookedTransaction
from ...domain.transaction.corporate_action import CORPORATE_ACTION_RECONCILIATION_INPUT_TYPES
from ...ports import (
    CorporateActionReconciliationEvidence,
    CorporateActionReconciliationKey,
)
from ..transaction_mapping.booked_transaction import to_booked_transaction_from_record

CORPORATE_ACTION_RECONCILIATION_RESOLUTION_ACTOR = "corporate-action-reconciliation"


class SqlAlchemyCorporateActionReconciliationRepository:
    """Load linked transactions and persist reconciliation evidence atomically."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load_group(
        self, key: CorporateActionReconciliationKey
    ) -> tuple[BookedTransaction, ...]:
        stmt = (
            select(DBTransaction)
            .join(Portfolio, Portfolio.portfolio_id == DBTransaction.portfolio_id)
            .where(Portfolio.tenant_id == key.tenant_id.value)
            .where(DBTransaction.portfolio_id == key.portfolio_id)
            .where(DBTransaction.linked_transaction_group_id == key.linked_transaction_group_id)
            .where(DBTransaction.parent_event_reference == key.parent_event_reference)
            .where(
                DBTransaction.transaction_type.in_(
                    tuple(sorted(CORPORATE_ACTION_RECONCILIATION_INPUT_TYPES))
                )
            )
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return tuple(
            replace(
                to_booked_transaction_from_record(row),
                tenant_id=key.tenant_id.value,
            )
            for row in rows
        )

    async def save_evidence(
        self,
        *,
        tenant_id: TenantId,
        evidence: CorporateActionReconciliationEvidence,
    ) -> None:
        if evidence.tenant_id != tenant_id:
            raise TenantAuthorityMismatchError(
                "reconciliation evidence tenant does not match admitted tenant authority"
            )
        run = {
            **asdict(evidence.run),
            "authority_scope": "TENANT",
            "tenant_id": tenant_id.value,
        }
        run_stmt = pg_insert(FinancialReconciliationRun).values(**run)
        run_result = await self._session.execute(
            run_stmt.on_conflict_do_update(
                index_elements=["run_id"],
                set_={
                    "status": run_stmt.excluded.status,
                    "summary": run_stmt.excluded.summary,
                    "failure_reason": run_stmt.excluded.failure_reason,
                    "completed_at": run_stmt.excluded.completed_at,
                    "updated_at": func.now(),
                },
                where=(
                    (FinancialReconciliationRun.authority_scope == "TENANT")
                    & (FinancialReconciliationRun.tenant_id == tenant_id.value)
                ),
            ).returning(FinancialReconciliationRun.run_id)
        )
        # PostgreSQL returns no row when the conflict WHERE rejects a foreign
        # authority. Treat that as an ownership violation, never a successful replay.
        if run_result.scalar_one_or_none() is None:
            raise TenantAuthorityMismatchError(
                "reconciliation run identity is bound to different tenant authority"
            )
        await self._resolve_superseded_findings(tenant_id=tenant_id, evidence=evidence)
        for finding in evidence.findings:
            finding_stmt = pg_insert(FinancialReconciliationFinding).values(
                **asdict(finding),
                authority_scope="TENANT",
                tenant_id=tenant_id.value,
            )
            finding_result = await self._session.execute(
                finding_stmt.on_conflict_do_update(
                    index_elements=["finding_id"],
                    set_={
                        "reconciliation_type": finding_stmt.excluded.reconciliation_type,
                        "finding_type": finding_stmt.excluded.finding_type,
                        "severity": finding_stmt.excluded.severity,
                        "portfolio_id": finding_stmt.excluded.portfolio_id,
                        "security_id": finding_stmt.excluded.security_id,
                        "transaction_id": finding_stmt.excluded.transaction_id,
                        "business_date": finding_stmt.excluded.business_date,
                        "epoch": finding_stmt.excluded.epoch,
                        "expected_value": finding_stmt.excluded.expected_value,
                        "observed_value": finding_stmt.excluded.observed_value,
                        "detail": finding_stmt.excluded.detail,
                        "owner": finding_stmt.excluded.owner,
                        "tolerance": finding_stmt.excluded.tolerance,
                        "observed_delta": finding_stmt.excluded.observed_delta,
                        "repair_recommendation": finding_stmt.excluded.repair_recommendation,
                    },
                    where=(
                        (FinancialReconciliationFinding.authority_scope == "TENANT")
                        & (FinancialReconciliationFinding.tenant_id == tenant_id.value)
                    ),
                ).returning(FinancialReconciliationFinding.finding_id)
            )
            # Keep finding identity collisions on the same fail-closed contract as runs.
            if finding_result.scalar_one_or_none() is None:
                raise TenantAuthorityMismatchError(
                    "reconciliation finding identity is bound to different tenant authority"
                )

    async def _resolve_superseded_findings(
        self,
        *,
        tenant_id: TenantId,
        evidence: CorporateActionReconciliationEvidence,
    ) -> None:
        linked_group = _required_summary_identity(
            evidence,
            "linked_transaction_group_id",
        )
        parent_reference = _required_summary_identity(
            evidence,
            "parent_event_reference",
        )
        stmt = (
            update(FinancialReconciliationFinding)
            .where(
                FinancialReconciliationFinding.authority_scope == "TENANT",
                FinancialReconciliationFinding.tenant_id == tenant_id.value,
                FinancialReconciliationFinding.reconciliation_type
                == evidence.run.reconciliation_type,
                FinancialReconciliationFinding.portfolio_id == evidence.run.portfolio_id,
                FinancialReconciliationFinding.run_id != evidence.run.run_id,
                FinancialReconciliationFinding.resolution_state.in_(("OPEN", "IN_PROGRESS")),
                FinancialReconciliationFinding.detail["linked_transaction_group_id"].as_string()
                == linked_group,
                FinancialReconciliationFinding.detail["parent_event_reference"].as_string()
                == parent_reference,
            )
            .values(
                resolution_state="RESOLVED",
                resolution_actor=CORPORATE_ACTION_RECONCILIATION_RESOLUTION_ACTOR,
                resolved_at=evidence.run.completed_at,
            )
        )
        await self._session.execute(stmt)


def _required_summary_identity(
    evidence: CorporateActionReconciliationEvidence,
    field_name: str,
) -> str:
    value = evidence.run.summary.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"Corporate-action reconciliation evidence is missing {field_name}: "
            f"{evidence.run.run_id}"
        )
    return value.strip()
