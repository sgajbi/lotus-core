"""SQLAlchemy adapter for corporate-action cost-basis reconciliation evidence."""

from dataclasses import asdict

from portfolio_common.database_models import (
    FinancialReconciliationFinding,
    FinancialReconciliationRun,
    Portfolio,
)
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain import BookedTransaction
from ...domain.transaction.corporate_action import CORPORATE_ACTION_RECONCILIATION_INPUT_TYPES
from ...ports import (
    CorporateActionReconciliationEvidence,
    CorporateActionReconciliationKey,
)
from ..transaction_mapping.booked_transaction import to_booked_transaction

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
            .where(Portfolio.tenant_id == key.tenant_id)
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
        return tuple(to_booked_transaction(TransactionEvent.model_validate(row)) for row in rows)

    async def save_evidence(self, evidence: CorporateActionReconciliationEvidence) -> None:
        run = {"tenant_id": evidence.tenant_id, **asdict(evidence.run)}
        run_stmt = pg_insert(FinancialReconciliationRun).values(**run)
        await self._session.execute(
            run_stmt.on_conflict_do_update(
                index_elements=["run_id"],
                set_={
                    "status": run_stmt.excluded.status,
                    "summary": run_stmt.excluded.summary,
                    "failure_reason": run_stmt.excluded.failure_reason,
                    "completed_at": run_stmt.excluded.completed_at,
                    "updated_at": func.now(),
                },
            )
        )
        await self._resolve_superseded_findings(evidence)
        for finding in evidence.findings:
            finding_stmt = pg_insert(FinancialReconciliationFinding).values(**asdict(finding))
            await self._session.execute(
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
                )
            )

    async def _resolve_superseded_findings(
        self,
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
                FinancialReconciliationFinding.reconciliation_type
                == evidence.run.reconciliation_type,
                FinancialReconciliationFinding.run_id.in_(
                    select(FinancialReconciliationRun.run_id).where(
                        FinancialReconciliationRun.tenant_id == evidence.tenant_id
                    )
                ),
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
