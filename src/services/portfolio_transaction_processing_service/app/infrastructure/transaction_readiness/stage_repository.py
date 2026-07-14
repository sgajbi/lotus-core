"""Persist transaction-processing stage readiness within the transaction boundary."""

from __future__ import annotations

from datetime import date
from typing import cast

from portfolio_common.database_models import PipelineStageState
from sqlalchemy import and_, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain import TransactionStageRecord


class SqlAlchemyTransactionStageRepository:
    """Store transaction stage state using epoch-fenced PostgreSQL operations."""

    def __init__(self, db_session: AsyncSession) -> None:
        self._db_session = db_session

    async def acquire_stage_lock(
        self,
        *,
        stage_name: str,
        portfolio_id: str,
        transaction_id: str,
    ) -> None:
        """Serialize updates for one portfolio transaction stage."""
        lock_identity = f"pipeline-stage:{stage_name}:{portfolio_id}:{transaction_id}"
        await self._db_session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_identity, 0))"),
            {"lock_identity": lock_identity},
        )

    async def latest_epoch(
        self,
        *,
        stage_name: str,
        portfolio_id: str,
        transaction_id: str,
    ) -> int | None:
        """Return the latest persisted epoch for one transaction stage."""
        statement = select(func.max(PipelineStageState.epoch)).where(
            PipelineStageState.stage_name == stage_name,
            PipelineStageState.portfolio_id == portfolio_id,
            PipelineStageState.transaction_id == transaction_id,
        )
        result = await self._db_session.execute(statement)
        return cast(int | None, result.scalar_one_or_none())

    async def upsert_processed_stage(
        self,
        *,
        stage_name: str,
        transaction_id: str,
        portfolio_id: str,
        security_id: str | None,
        business_date: date,
        epoch: int,
    ) -> TransactionStageRecord:
        """Record processing completion without allowing a stage key to change owner."""
        statement = (
            pg_insert(PipelineStageState)
            .values(
                stage_name=stage_name,
                transaction_id=transaction_id,
                portfolio_id=portfolio_id,
                security_id=security_id,
                business_date=business_date,
                epoch=epoch,
                status="PENDING",
                cost_event_seen=True,
                cashflow_event_seen=True,
                last_source_event_type="processed_transaction",
            )
            .on_conflict_do_update(
                index_elements=["stage_name", "transaction_id", "epoch"],
                set_={
                    "portfolio_id": PipelineStageState.portfolio_id,
                    "security_id": security_id,
                    "business_date": business_date,
                    "cost_event_seen": True,
                    "cashflow_event_seen": True,
                    "last_source_event_type": "processed_transaction",
                },
            )
            .returning(PipelineStageState)
        )
        result = await self._db_session.execute(statement.execution_options(populate_existing=True))
        stage = result.scalar_one()
        if stage.portfolio_id != portfolio_id:
            raise ValueError(
                "Pipeline stage key collision detected for different portfolios: "
                f"{stage_name}/{transaction_id}/{epoch} "
                f"existing={stage.portfolio_id} incoming={portfolio_id}"
            )
        return _to_transaction_stage_record(stage)

    async def claim_completion(self, stage: TransactionStageRecord) -> bool:
        """Atomically claim emission for a pending, processed transaction stage."""
        statement = (
            update(PipelineStageState)
            .where(
                and_(
                    PipelineStageState.id == stage.stage_id,
                    PipelineStageState.status == "PENDING",
                    PipelineStageState.cost_event_seen.is_(True),
                )
            )
            .values(status="COMPLETED", ready_emitted_at=func.now())
        )
        result = cast(CursorResult[tuple[object, ...]], await self._db_session.execute(statement))
        claimed = cast(int, result.rowcount) == 1
        return claimed


def _to_transaction_stage_record(stage: PipelineStageState) -> TransactionStageRecord:
    """Map persistence state to the transaction capability's domain record."""
    return TransactionStageRecord(
        stage_id=stage.id,
        transaction_id=stage.transaction_id,
        portfolio_id=stage.portfolio_id,
        security_id=stage.security_id,
        business_date=stage.business_date,
        epoch=stage.epoch,
        status=stage.status,
        cost_event_seen=stage.cost_event_seen,
    )
