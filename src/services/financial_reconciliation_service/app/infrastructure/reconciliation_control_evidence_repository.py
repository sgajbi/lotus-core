"""SQLAlchemy adapter for durable financial reconciliation control evidence."""

from __future__ import annotations

from datetime import date
from typing import cast

from portfolio_common.database_models import PipelineStageState
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.reconciliation_control import (
    FINANCIAL_RECONCILIATION_SOURCE_EVENT,
    FINANCIAL_RECONCILIATION_STAGE,
    FinancialReconciliationCompletion,
    RecordedReconciliationControl,
    merge_control_status,
)


class SqlAlchemyReconciliationControlEvidenceRepository:
    """Store reconciliation evidence in the existing supportability table."""

    def __init__(self, db_session: AsyncSession) -> None:
        self._db_session = db_session

    async def record_completion(
        self,
        completion: FinancialReconciliationCompletion,
    ) -> RecordedReconciliationControl:
        """Upsert one epoch monotonically and return the latest known epoch."""

        stage_key = self.build_stage_key(
            portfolio_id=completion.portfolio_id,
            business_date=completion.business_date,
        )
        insert_statement = (
            pg_insert(PipelineStageState)
            .values(
                stage_name=FINANCIAL_RECONCILIATION_STAGE,
                transaction_id=stage_key,
                portfolio_id=completion.portfolio_id,
                security_id=None,
                business_date=completion.business_date,
                epoch=completion.epoch,
                status=completion.outcome_status,
                cost_event_seen=False,
                cashflow_event_seen=False,
                ready_emitted_at=func.now(),
                last_source_event_type=FINANCIAL_RECONCILIATION_SOURCE_EVENT,
            )
            .on_conflict_do_nothing(index_elements=["stage_name", "transaction_id", "epoch"])
        )
        await self._db_session.execute(insert_statement)
        stage = (
            await self._db_session.execute(
                select(PipelineStageState)
                .where(
                    PipelineStageState.stage_name == FINANCIAL_RECONCILIATION_STAGE,
                    PipelineStageState.transaction_id == stage_key,
                    PipelineStageState.epoch == completion.epoch,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        if stage.portfolio_id != completion.portfolio_id:
            raise ValueError(
                "Reconciliation control stage key collision for different portfolios: "
                f"{stage_key}/{completion.epoch} existing={stage.portfolio_id} "
                f"incoming={completion.portfolio_id}"
            )
        stage.status = merge_control_status(stage.status, completion.outcome_status)
        stage.security_id = None
        stage.business_date = completion.business_date
        stage.last_source_event_type = FINANCIAL_RECONCILIATION_SOURCE_EVENT
        if stage.ready_emitted_at is None:
            stage.ready_emitted_at = func.now()
        await self._db_session.flush()
        await self._db_session.refresh(stage)

        latest_epoch_statement = select(func.max(PipelineStageState.epoch)).where(
            PipelineStageState.stage_name == FINANCIAL_RECONCILIATION_STAGE,
            PipelineStageState.portfolio_id == completion.portfolio_id,
            PipelineStageState.business_date == completion.business_date,
        )
        latest_epoch = cast(
            int | None,
            (await self._db_session.execute(latest_epoch_statement)).scalar_one_or_none(),
        )
        return RecordedReconciliationControl(
            status=stage.status,
            latest_epoch=latest_epoch,
        )

    @staticmethod
    def build_stage_key(*, portfolio_id: str, business_date: date) -> str:
        """Build the compatibility-preserving portfolio control-stage key."""

        return (
            f"portfolio-stage:{FINANCIAL_RECONCILIATION_STAGE}:"
            f"{portfolio_id}:{business_date.isoformat()}"
        )
