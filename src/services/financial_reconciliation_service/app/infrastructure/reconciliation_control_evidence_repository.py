"""SQLAlchemy adapter for durable financial reconciliation control evidence."""

from __future__ import annotations

from datetime import date
from typing import cast

from portfolio_common.database_models import PipelineStageState
from portfolio_common.reconciliation_quality import (
    FINANCIAL_RECONCILIATION_SOURCE_EVENT,
    FINANCIAL_RECONCILIATION_STAGE,
)
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.reconciliation_control import (
    FinancialReconciliationCompletion,
    RecordedReconciliationControl,
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
                aggregation_revision=completion.aggregation_revision,
                status=completion.outcome_status,
                cost_event_seen=False,
                cashflow_event_seen=False,
                ready_emitted_at=func.now(),
                last_source_event_type=FINANCIAL_RECONCILIATION_SOURCE_EVENT,
            )
            .on_conflict_do_nothing(index_elements=["stage_name", "transaction_id", "epoch"])
        )
        insert_result = await self._db_session.execute(insert_statement)
        created = int(insert_result.rowcount or 0) == 1
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
        current_revision = int(stage.aggregation_revision or 0)
        accepted_revision = created or completion.aggregation_revision > current_revision
        if completion.aggregation_revision == current_revision and not created:
            if stage.status != completion.outcome_status:
                raise ValueError(
                    "Conflicting reconciliation outcomes for one aggregation revision: "
                    f"{stage_key}/{completion.epoch}/{completion.aggregation_revision} "
                    f"existing={stage.status} incoming={completion.outcome_status}"
                )
        if accepted_revision:
            stage.status = completion.outcome_status
            stage.aggregation_revision = completion.aggregation_revision
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
            accepted_revision=accepted_revision,
        )

    @staticmethod
    def build_stage_key(*, portfolio_id: str, business_date: date) -> str:
        """Build the compatibility-preserving portfolio control-stage key."""

        return (
            f"portfolio-stage:{FINANCIAL_RECONCILIATION_STAGE}:"
            f"{portfolio_id}:{business_date.isoformat()}"
        )
