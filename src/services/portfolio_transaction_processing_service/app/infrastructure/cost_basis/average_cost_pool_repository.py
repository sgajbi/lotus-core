"""SQLAlchemy persistence for average-cost pool state and source lots."""

from decimal import Decimal
from typing import Any

from portfolio_common.database_models import AverageCostPoolState, PositionLotState
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent
from portfolio_common.identifiers import normalize_lookup_identifier
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.cost_basis import (
    AverageCostPoolCheckpoint,
    AverageCostPoolRebuildPlan,
    AverageCostPoolTransition,
    OpenLotState,
)
from ...ports import AverageCostPoolCheckpointRecord, AverageCostPoolPersistedSummary
from ..transaction_mapping.booked_transaction import to_booked_transaction
from .lot_state_mapper import buy_lot_state_payload, mutable_lot_state_fields
from .lot_state_repository import SqlAlchemyCostBasisLotRepository


def _scaled_persisted_value(
    column: Any,
    *,
    before: Decimal,
    after: Decimal,
    round_down: bool,
) -> Any:
    if after == before:
        return column
    if after == Decimal(0):
        return Decimal(0)
    if before <= Decimal(0):
        raise ValueError("Average cost source scaling requires a positive prior aggregate")
    scaled = column * after / before
    return func.trunc(scaled, 10) if round_down else func.round(scaled, 10)


class SqlAlchemyAverageCostPoolRepository:
    """Persist one portfolio-security average-cost aggregate and its source lots."""

    REBUILD_UPSERT_CHUNK_SIZE = 500

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._lot_states = SqlAlchemyCostBasisLotRepository(session)

    async def get_average_cost_pool_checkpoint_record(
        self,
        *,
        portfolio_id: str,
        security_id: str,
    ) -> AverageCostPoolCheckpointRecord | None:
        """Lock and load the current pool with its representative transaction."""

        statement = (
            select(AverageCostPoolState, DBTransaction)
            .outerjoin(
                DBTransaction,
                DBTransaction.transaction_id
                == AverageCostPoolState.representative_source_transaction_id,
            )
            .where(
                AverageCostPoolState.portfolio_id == normalize_lookup_identifier(portfolio_id),
                AverageCostPoolState.security_id == normalize_lookup_identifier(security_id),
            )
            .with_for_update(of=AverageCostPoolState)
        )
        row = (await self._session.execute(statement)).first()
        if row is None:
            return None
        state, representative_transaction = row
        return AverageCostPoolCheckpointRecord(
            checkpoint=AverageCostPoolCheckpoint(
                portfolio_id=state.portfolio_id,
                instrument_id=state.instrument_id,
                security_id=state.security_id,
                representative_source_transaction_id=(state.representative_source_transaction_id),
                quantity=state.pool_quantity,
                cost_local=state.pool_cost_local,
                cost_base=state.pool_cost_base,
                state_version=state.state_version,
            ),
            representative_transaction=(
                to_booked_transaction(TransactionEvent.model_validate(representative_transaction))
                if representative_transaction is not None
                else None
            ),
        )

    async def upsert_average_cost_pool_checkpoint(
        self,
        checkpoint: AverageCostPoolCheckpoint,
    ) -> None:
        """Idempotently persist the current average-cost aggregate checkpoint."""

        payload = {
            "portfolio_id": normalize_lookup_identifier(checkpoint.portfolio_id),
            "security_id": normalize_lookup_identifier(checkpoint.security_id),
            "instrument_id": normalize_lookup_identifier(checkpoint.instrument_id),
            "representative_source_transaction_id": (
                normalize_lookup_identifier(checkpoint.representative_source_transaction_id)
                if checkpoint.representative_source_transaction_id
                else None
            ),
            "pool_quantity": checkpoint.quantity,
            "pool_cost_local": checkpoint.cost_local,
            "pool_cost_base": checkpoint.cost_base,
            "state_version": checkpoint.state_version,
        }
        statement = pg_insert(AverageCostPoolState).values(**payload)
        await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=["portfolio_id", "security_id"],
                set_={
                    field_name: getattr(statement.excluded, field_name)
                    for field_name in payload
                    if field_name not in {"portfolio_id", "security_id"}
                }
                | {"updated_at": func.now()},
            )
        )

    async def apply_average_cost_pool_transition(
        self,
        transition: AverageCostPoolTransition,
    ) -> None:
        """Persist one incremental pool and source-lot state transition atomically."""

        await self._scale_existing_average_cost_sources(transition)
        if transition.explicit_sources_after:
            await self.update_selected_open_lot_states(
                portfolio_id=transition.before.portfolio_id,
                security_id=transition.before.security_id,
                states_by_source_transaction_id=dict(transition.explicit_sources_after),
            )
        await self.upsert_average_cost_pool_checkpoint(transition.after)

    async def apply_average_cost_pool_rebuild(
        self,
        plan: AverageCostPoolRebuildPlan,
    ) -> None:
        """Replace the durable pool and source-lot snapshot in bounded batches."""

        checkpoint = plan.checkpoint
        normalized_portfolio_id = normalize_lookup_identifier(checkpoint.portfolio_id)
        normalized_security_id = normalize_lookup_identifier(checkpoint.security_id)
        await self._session.execute(
            update(PositionLotState)
            .where(
                func.trim(PositionLotState.portfolio_id) == normalized_portfolio_id,
                func.trim(PositionLotState.security_id) == normalized_security_id,
            )
            .values(
                open_quantity=Decimal(0),
                lot_cost_local=Decimal(0),
                lot_cost_base=Decimal(0),
                updated_at=func.now(),
            )
        )

        payloads = []
        for source_transaction in plan.source_transactions:
            payload = buy_lot_state_payload(source_transaction)
            state = plan.source_states.get(source_transaction.transaction_id)
            payload.update(
                open_quantity=state.quantity if state is not None else Decimal(0),
                lot_cost_local=state.cost_local if state is not None else Decimal(0),
                lot_cost_base=state.cost_base if state is not None else Decimal(0),
            )
            payloads.append(payload)
        for offset in range(0, len(payloads), self.REBUILD_UPSERT_CHUNK_SIZE):
            statement = pg_insert(PositionLotState).values(
                payloads[offset : offset + self.REBUILD_UPSERT_CHUNK_SIZE]
            )
            await self._session.execute(
                statement.on_conflict_do_update(
                    index_elements=["source_transaction_id"],
                    set_=mutable_lot_state_fields(statement),
                )
            )

        await self.upsert_average_cost_pool_checkpoint(checkpoint)

    async def get_average_cost_pool_persisted_summary(
        self,
        *,
        portfolio_id: str,
        security_id: str,
    ) -> AverageCostPoolPersistedSummary:
        """Summarize persisted pool and source lots for reconciliation."""

        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        normalized_security_id = normalize_lookup_identifier(security_id)
        pool = (
            (
                await self._session.execute(
                    select(AverageCostPoolState).where(
                        AverageCostPoolState.portfolio_id == normalized_portfolio_id,
                        AverageCostPoolState.security_id == normalized_security_id,
                    )
                )
            )
            .scalars()
            .first()
        )
        source_count, source_quantity, source_cost_local, source_cost_base = (
            await self._session.execute(
                select(
                    func.count(PositionLotState.id),
                    func.coalesce(func.sum(PositionLotState.open_quantity), Decimal(0)),
                    func.coalesce(func.sum(PositionLotState.lot_cost_local), Decimal(0)),
                    func.coalesce(func.sum(PositionLotState.lot_cost_base), Decimal(0)),
                ).where(
                    func.trim(PositionLotState.portfolio_id) == normalized_portfolio_id,
                    func.trim(PositionLotState.security_id) == normalized_security_id,
                )
            )
        ).one()
        return AverageCostPoolPersistedSummary(
            source_count=int(source_count),
            source_quantity=source_quantity,
            source_cost_local=source_cost_local,
            source_cost_base=source_cost_base,
            pool_quantity=pool.pool_quantity if pool is not None else None,
            pool_cost_local=pool.pool_cost_local if pool is not None else None,
            pool_cost_base=pool.pool_cost_base if pool is not None else None,
        )

    async def update_selected_open_lot_states(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        states_by_source_transaction_id: dict[str, OpenLotState],
    ) -> None:
        """Update selected pool source lots without closing omitted open lots."""
        await self._lot_states.update_selected_open_lot_states(
            portfolio_id=portfolio_id,
            security_id=security_id,
            states_by_source_transaction_id=states_by_source_transaction_id,
        )

    async def _scale_existing_average_cost_sources(
        self,
        transition: AverageCostPoolTransition,
    ) -> None:
        before = transition.before
        after = transition.existing_sources_after
        if before.quantity == Decimal(0) or after == before.as_open_lot_state():
            return

        predicates = [
            func.trim(PositionLotState.portfolio_id)
            == normalize_lookup_identifier(before.portfolio_id),
            func.trim(PositionLotState.security_id)
            == normalize_lookup_identifier(before.security_id),
        ]
        explicit_source_ids = set(transition.explicit_sources_after)
        if explicit_source_ids:
            predicates.append(PositionLotState.source_transaction_id.not_in(explicit_source_ids))

        if after.quantity == Decimal(0):
            result = await self._session.execute(
                update(PositionLotState)
                .where(*predicates)
                .values(
                    open_quantity=Decimal(0),
                    lot_cost_local=Decimal(0),
                    lot_cost_base=Decimal(0),
                    updated_at=func.now(),
                )
            )
            if result.rowcount < 1:
                raise ValueError("Average cost pool close found no persisted source lots")
            return

        representative_source_id = before.representative_source_transaction_id
        if representative_source_id is None:
            raise ValueError("Open average cost pool has no representative source")
        non_residual_predicates = [
            *predicates,
            PositionLotState.source_transaction_id != representative_source_id,
        ]
        await self._session.execute(
            update(PositionLotState)
            .where(*non_residual_predicates)
            .values(
                open_quantity=_scaled_persisted_value(
                    PositionLotState.open_quantity,
                    before=before.quantity,
                    after=after.quantity,
                    round_down=True,
                ),
                lot_cost_local=_scaled_persisted_value(
                    PositionLotState.lot_cost_local,
                    before=before.cost_local,
                    after=after.cost_local,
                    round_down=False,
                ),
                lot_cost_base=_scaled_persisted_value(
                    PositionLotState.lot_cost_base,
                    before=before.cost_base,
                    after=after.cost_base,
                    round_down=False,
                ),
                updated_at=func.now(),
            )
        )
        allocated_quantity, allocated_cost_local, allocated_cost_base = (
            await self._session.execute(
                select(
                    func.coalesce(func.sum(PositionLotState.open_quantity), Decimal(0)),
                    func.coalesce(func.sum(PositionLotState.lot_cost_local), Decimal(0)),
                    func.coalesce(func.sum(PositionLotState.lot_cost_base), Decimal(0)),
                ).where(*non_residual_predicates)
            )
        ).one()
        residual_state = OpenLotState(
            quantity=after.quantity - allocated_quantity,
            cost_local=after.cost_local - allocated_cost_local,
            cost_base=after.cost_base - allocated_cost_base,
        )
        if (
            residual_state.quantity < Decimal(0)
            or residual_state.cost_local < Decimal(0)
            or residual_state.cost_base < Decimal(0)
        ):
            raise ValueError("Average cost source allocation exceeds the target pool aggregate")
        residual_result = await self._session.execute(
            update(PositionLotState)
            .where(
                *predicates,
                PositionLotState.source_transaction_id == representative_source_id,
            )
            .values(
                open_quantity=residual_state.quantity,
                lot_cost_local=residual_state.cost_local,
                lot_cost_base=residual_state.cost_base,
                updated_at=func.now(),
            )
        )
        if residual_result.rowcount != 1:
            raise ValueError("Average cost pool representative source was not updated exactly once")
