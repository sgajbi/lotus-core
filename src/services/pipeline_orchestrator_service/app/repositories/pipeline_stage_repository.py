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
                    "portfolio_id": PipelineStageState.portfolio_id,
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
        if stage.portfolio_id != portfolio_id:
            raise ValueError(
                "Pipeline stage key collision detected for different portfolios: "
                f"{stage_name}/{transaction_id}/{epoch} "
                f"existing={stage.portfolio_id} incoming={portfolio_id}"
            )
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

    async def upsert_portfolio_control_stage_status(
        self,
        *,
        stage_name: str,
        portfolio_id: str,
        business_date: date,
        epoch: int,
        status: str,
        source_event_type: str,
    ) -> PipelineStageState:
        transaction_id = self.build_portfolio_stage_key(
            stage_name=stage_name,
            portfolio_id=portfolio_id,
            business_date=business_date,
        )
        insert_stmt = (
            pg_insert(PipelineStageState)
            .values(
                stage_name=stage_name,
                transaction_id=transaction_id,
                portfolio_id=portfolio_id,
                security_id=None,
                business_date=business_date,
                epoch=epoch,
                status=status,
                cost_event_seen=False,
                cashflow_event_seen=False,
                ready_emitted_at=func.now(),
                last_source_event_type=source_event_type,
            )
            .on_conflict_do_nothing(index_elements=["stage_name", "transaction_id", "epoch"])
        )
        await self.db.execute(insert_stmt)
        result = await self.db.execute(
            select(PipelineStageState)
            .where(
                PipelineStageState.stage_name == stage_name,
                PipelineStageState.transaction_id == transaction_id,
                PipelineStageState.epoch == epoch,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        stage = result.scalar_one()
        if stage.portfolio_id != portfolio_id:
            raise ValueError(
                "Pipeline control stage key collision detected for different portfolios: "
                f"{stage_name}/{transaction_id}/{epoch} "
                f"existing={stage.portfolio_id} incoming={portfolio_id}"
            )
        merged_status = self.merge_portfolio_control_status(stage.status, status)
        stage.status = merged_status
        stage.security_id = None
        stage.business_date = business_date
        stage.last_source_event_type = source_event_type
        if stage.ready_emitted_at is None:
            stage.ready_emitted_at = func.now()
        await self.db.flush()
        await self.db.refresh(stage)
        return stage

    async def get_latest_portfolio_control_stage_epoch(
        self,
        *,
        stage_name: str,
        portfolio_id: str,
        business_date: date,
    ) -> int | None:
        stmt = select(func.max(PipelineStageState.epoch)).where(
            PipelineStageState.stage_name == stage_name,
            PipelineStageState.portfolio_id == portfolio_id,
            PipelineStageState.business_date == business_date,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    @staticmethod
    def build_portfolio_stage_key(
        *,
        stage_name: str,
        portfolio_id: str,
        business_date: date,
    ) -> str:
        return f"portfolio-stage:{stage_name}:{portfolio_id}:{business_date.isoformat()}"

    @staticmethod
    def merge_portfolio_control_status(existing_status: str, incoming_status: str) -> str:
        rank = {
            "PENDING": 0,
            "COMPLETED": 1,
            "REQUIRES_REPLAY": 2,
            "FAILED": 3,
        }
        existing_rank = rank.get(existing_status, 0)
        incoming_rank = rank.get(incoming_status, 0)
        return existing_status if existing_rank >= incoming_rank else incoming_status
