"""Persist transaction-processing stage readiness within the transaction boundary."""

from __future__ import annotations

from datetime import date
from typing import cast

from portfolio_common.database_models import PipelineStageState
from sqlalchemy import select, text
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

    async def claim_processed_stage(
        self,
        *,
        stage_name: str,
        transaction_id: str,
        portfolio_id: str,
        security_id: str | None,
        business_date: date,
        epoch: int,
    ) -> TransactionStageRecord | None:
        """Persist and claim a current completion in one post-lock statement.

        The advisory lock remains a separate statement so READ COMMITTED takes a fresh
        snapshot after a concurrent owner commits. The common path therefore uses two
        database round trips instead of lock, epoch read, upsert, and completion update.
        """
        parameters = {
            "stage_name": stage_name,
            "transaction_id": transaction_id,
            "portfolio_id": portfolio_id,
            "security_id": security_id,
            "business_date": business_date,
            "epoch": epoch,
        }
        result = await self._db_session.execute(
            text(
                """
                WITH existing AS MATERIALIZED (
                    SELECT status
                    FROM pipeline_stage_state
                    WHERE stage_name = CAST(:stage_name AS varchar)
                      AND transaction_id = CAST(:transaction_id AS varchar)
                      AND epoch = CAST(:epoch AS integer)
                ),
                claimed AS (
                    INSERT INTO pipeline_stage_state (
                        stage_name,
                        transaction_id,
                        portfolio_id,
                        security_id,
                        business_date,
                        epoch,
                        status,
                        cost_event_seen,
                        cashflow_event_seen,
                        ready_emitted_at,
                        last_source_event_type
                    )
                    SELECT
                        CAST(:stage_name AS varchar),
                        CAST(:transaction_id AS varchar),
                        CAST(:portfolio_id AS varchar),
                        CAST(:security_id AS varchar),
                        CAST(:business_date AS date),
                        CAST(:epoch AS integer),
                        'COMPLETED',
                        true,
                        true,
                        now(),
                        'processed_transaction'
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM pipeline_stage_state
                        WHERE stage_name = CAST(:stage_name AS varchar)
                          AND portfolio_id = CAST(:portfolio_id AS varchar)
                          AND transaction_id = CAST(:transaction_id AS varchar)
                          AND epoch > CAST(:epoch AS integer)
                    )
                    ON CONFLICT (stage_name, transaction_id, epoch) DO UPDATE
                    SET
                        security_id = EXCLUDED.security_id,
                        business_date = EXCLUDED.business_date,
                        status = 'COMPLETED',
                        cost_event_seen = true,
                        cashflow_event_seen = true,
                        ready_emitted_at = CASE
                            WHEN pipeline_stage_state.status <> 'COMPLETED' THEN now()
                            ELSE pipeline_stage_state.ready_emitted_at
                        END,
                        last_source_event_type = 'processed_transaction',
                        updated_at = CASE
                            WHEN pipeline_stage_state.status <> 'COMPLETED'
                              OR pipeline_stage_state.cost_event_seen IS NOT true
                              OR pipeline_stage_state.cashflow_event_seen IS NOT true
                              OR pipeline_stage_state.security_id
                                  IS DISTINCT FROM EXCLUDED.security_id
                              OR pipeline_stage_state.business_date
                                  IS DISTINCT FROM EXCLUDED.business_date
                            THEN now()
                            ELSE pipeline_stage_state.updated_at
                        END
                    WHERE pipeline_stage_state.portfolio_id = EXCLUDED.portfolio_id
                    RETURNING
                        id,
                        transaction_id,
                        portfolio_id,
                        security_id,
                        business_date,
                        epoch,
                        status,
                        cost_event_seen
                )
                SELECT
                    claimed.*,
                    coalesce(existing.status <> 'COMPLETED', true) AS newly_claimed
                FROM claimed
                LEFT JOIN existing ON true
                """
            ),
            parameters,
        )
        claimed = result.mappings().one_or_none()
        if claimed is not None:
            if not claimed["newly_claimed"]:
                return None
            return TransactionStageRecord(
                stage_id=claimed["id"],
                transaction_id=claimed["transaction_id"],
                portfolio_id=claimed["portfolio_id"],
                security_id=claimed["security_id"],
                business_date=claimed["business_date"],
                epoch=claimed["epoch"],
                status=claimed["status"],
                cost_event_seen=claimed["cost_event_seen"],
            )

        owner_result = await self._db_session.execute(
            select(PipelineStageState.portfolio_id).where(
                PipelineStageState.stage_name == stage_name,
                PipelineStageState.transaction_id == transaction_id,
                PipelineStageState.epoch == epoch,
            )
        )
        owner = cast(str | None, owner_result.scalar_one_or_none())
        if owner is not None and owner != portfolio_id:
            raise ValueError(
                "Pipeline stage key collision detected for different portfolios: "
                f"{stage_name}/{transaction_id}/{epoch} "
                f"existing={owner} incoming={portfolio_id}"
            )
        return None
