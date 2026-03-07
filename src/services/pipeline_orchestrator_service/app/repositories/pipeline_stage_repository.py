from datetime import date

from portfolio_common.database_models import PipelineStageState
from sqlalchemy import and_, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession


class PipelineStageRepository:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def upsert_stage_flags(
        self,
        *,
        stage_name: str,
        transaction_id: str,
        portfolio_id: str,
        security_id: str | None,
        business_date: date,
        epoch: int,
        source_event_type: str,
        cost_event_seen: bool,
        cashflow_event_seen: bool,
    ) -> PipelineStageState:
        stmt = (
            pg_insert(PipelineStageState)
            .values(
                stage_name=stage_name,
                transaction_id=transaction_id,
                portfolio_id=portfolio_id,
                security_id=security_id,
                business_date=business_date,
                epoch=epoch,
                status="PENDING",
                cost_event_seen=cost_event_seen,
                cashflow_event_seen=cashflow_event_seen,
                last_source_event_type=source_event_type,
            )
            .on_conflict_do_update(
                index_elements=["stage_name", "transaction_id", "epoch"],
                set_={
                    "portfolio_id": portfolio_id,
                    "security_id": security_id,
                    "business_date": business_date,
                    "cost_event_seen": PipelineStageState.cost_event_seen | cost_event_seen,
                    "cashflow_event_seen": PipelineStageState.cashflow_event_seen
                    | cashflow_event_seen,
                    "last_source_event_type": source_event_type,
                },
            )
        )
        await self.db.execute(stmt)

        result = await self.db.execute(
            select(PipelineStageState)
            .where(
                PipelineStageState.stage_name == stage_name,
                PipelineStageState.transaction_id == transaction_id,
                PipelineStageState.epoch == epoch,
            )
            .execution_options(populate_existing=True)
        )
        stage = result.scalar_one()
        await self.db.refresh(stage)
        return stage

    async def mark_stage_completed(self, stage_state: PipelineStageState) -> None:
        stage_state.status = "COMPLETED"
        stage_state.ready_emitted_at = func.now()

    async def mark_stage_completed_if_pending(self, stage_state: PipelineStageState) -> bool:
        stmt = (
            update(PipelineStageState)
            .where(
                and_(
                    PipelineStageState.id == stage_state.id,
                    PipelineStageState.status == "PENDING",
                    PipelineStageState.cost_event_seen.is_(True),
                    PipelineStageState.cashflow_event_seen.is_(True),
                )
            )
            .values(status="COMPLETED", ready_emitted_at=func.now())
        )
        result = await self.db.execute(stmt)
        claimed = result.rowcount == 1
        if claimed:
            stage_state.status = "COMPLETED"
        return claimed
