"""SQLAlchemy adapter for corporate-action cost-basis reconciliation evidence."""

from dataclasses import asdict

from portfolio_common.database_models import (
    FinancialReconciliationFinding,
    FinancialReconciliationRun,
)
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain import BookedTransaction
from ...ports import (
    CorporateActionReconciliationEvidence,
    CorporateActionReconciliationKey,
)
from ..transaction_mapping.booked_transaction import to_booked_transaction


class SqlAlchemyCorporateActionReconciliationRepository:
    """Load linked transactions and persist reconciliation evidence atomically."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load_group(
        self, key: CorporateActionReconciliationKey
    ) -> tuple[BookedTransaction, ...]:
        stmt = (
            select(DBTransaction)
            .where(DBTransaction.portfolio_id == key.portfolio_id)
            .where(DBTransaction.linked_transaction_group_id == key.linked_transaction_group_id)
            .where(DBTransaction.parent_event_reference == key.parent_event_reference)
            .where(
                DBTransaction.transaction_type.in_(
                    ("SPIN_OFF", "SPIN_IN", "DEMERGER_OUT", "DEMERGER_IN", "CASH_CONSIDERATION")
                )
            )
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return tuple(to_booked_transaction(TransactionEvent.model_validate(row)) for row in rows)

    async def save_evidence(self, evidence: CorporateActionReconciliationEvidence) -> None:
        run = asdict(evidence.run)
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
                    },
                )
            )
