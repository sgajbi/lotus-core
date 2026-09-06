"""SQLAlchemy persistence for average-cost pool state and source lots."""

from dataclasses import replace
from decimal import Decimal
from typing import Any

from portfolio_common.database_models import AverageCostPoolState, PositionLotState
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    calculation_lineage_binds_output,
    calculation_lineage_from_payload,
)
from portfolio_common.domain.transaction.numeric_policy import COST_BASIS_STATE_LEDGER_OUTPUT_V1
from portfolio_common.identifiers import normalize_lookup_identifier
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.cost_basis import (
    AverageCostPoolCheckpoint,
    AverageCostPoolRebuildPlan,
    AverageCostPoolTransition,
    OpenLotState,
    build_average_cost_pool_rebuild_lineage,
)
from ...domain.cost_basis.state_lineage import (
    CostBasisStateTransitionEvidence,
    build_cost_basis_state_lineage,
    canonical_cost_basis_output_payload,
)
from ...ports import AverageCostPoolCheckpointRecord, AverageCostPoolPersistedSummary
from ..transaction_mapping.booked_transaction import to_booked_transaction_from_record
from .lot_state_lineage import (
    LOT_STATE_LINEAGE_OUTPUT_FIELDS,
    lot_state_lineage_output_from_mapping,
    lot_state_lineage_output_from_row,
)
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
                calculation_lineage=calculation_lineage_from_payload(state.calculation_lineage),
            ),
            representative_transaction=(
                to_booked_transaction_from_record(representative_transaction)
                if representative_transaction is not None
                else None
            ),
        )

    async def upsert_average_cost_pool_checkpoint(
        self,
        checkpoint: AverageCostPoolCheckpoint,
    ) -> None:
        """Idempotently persist the current average-cost aggregate checkpoint."""

        lineage = checkpoint.calculation_lineage or build_cost_basis_state_lineage(
            algorithm_id="average-cost-pool-checkpoint-materialization",
            input_payload={"checkpoint_state": _checkpoint_payload(checkpoint)},
            output_payload=_checkpoint_payload(checkpoint),
        )
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
            "calculation_lineage": lineage.lineage_payload(),
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
        *,
        transition_evidence: CostBasisStateTransitionEvidence,
    ) -> None:
        """Persist one incremental pool and source-lot state transition atomically."""

        after = transition.after
        transition_lineage = build_cost_basis_state_lineage(
            algorithm_id="average-cost-pool-transition",
            input_payload={
                "application_transition_evidence": transition_evidence.lineage_payload(),
                "before": _checkpoint_payload(transition.before),
                "existing_sources_after": _open_lot_state_payload(
                    transition.existing_sources_after
                ),
                "explicit_sources_after": {
                    source_id: _open_lot_state_payload(state)
                    for source_id, state in transition.explicit_sources_after.items()
                },
            },
            output_payload=_checkpoint_payload(after),
        )
        await self._scale_existing_average_cost_sources(
            transition,
            transition_lineage=transition_lineage,
        )
        if transition.explicit_sources_after:
            await self.update_selected_open_lot_states(
                portfolio_id=transition.before.portfolio_id,
                security_id=transition.before.security_id,
                states_by_source_transaction_id=dict(transition.explicit_sources_after),
                transition_evidence=transition_evidence,
            )
        await self.upsert_average_cost_pool_checkpoint(
            replace(after, calculation_lineage=transition_lineage)
        )

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
                calculation_lineage=None,
                updated_at=func.now(),
            )
        )

        payloads = []
        for source_transaction in plan.source_transactions:
            payload = buy_lot_state_payload(source_transaction)
            state = plan.source_states.get(source_transaction.transaction_id)
            # The planner emits a state for every governed source, including closed sources;
            # this fallback is limited to defensive reconstruction of an omitted source.
            payload.update(
                original_quantity=(
                    state.original_quantity if state is not None else payload["original_quantity"]
                ),
                open_quantity=state.quantity if state is not None else Decimal(0),
                lot_cost_local=state.cost_local if state is not None else Decimal(0),
                lot_cost_base=state.cost_base if state is not None else Decimal(0),
            )
            source_lineage = build_cost_basis_state_lineage(
                algorithm_id="average-cost-source-rebuild",
                input_payload={
                    "processing_checkpoint": {
                        "calculation_state_version": (
                            plan.processing_checkpoint.calculation_state_version
                        ),
                        "latest_transaction_id": plan.processing_checkpoint.latest_transaction_id,
                    },
                    "replay_lineage": plan.replay_lineage.lineage_payload(),
                    "source_transaction_id": source_transaction.transaction_id,
                },
                output_payload=lot_state_lineage_output_from_mapping(payload),
            )
            payload["calculation_lineage"] = source_lineage.lineage_payload()
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

        checkpoint_lineage = build_average_cost_pool_rebuild_lineage(
            replay_lineage=plan.replay_lineage,
            checkpoint=checkpoint,
        )
        await self.upsert_average_cost_pool_checkpoint(
            replace(checkpoint, calculation_lineage=checkpoint_lineage)
        )

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
        source_rows = (
            await self._session.execute(
                select(
                    *(
                        getattr(PositionLotState, field)
                        for field in LOT_STATE_LINEAGE_OUTPUT_FIELDS
                    ),
                    PositionLotState.calculation_lineage,
                )
                .where(
                    func.trim(PositionLotState.portfolio_id) == normalized_portfolio_id,
                    func.trim(PositionLotState.security_id) == normalized_security_id,
                )
                .order_by(PositionLotState.source_transaction_id)
            )
        ).all()
        source_count = len(source_rows)
        source_quantity = sum((row.open_quantity for row in source_rows), Decimal(0))
        source_cost_local = sum((row.lot_cost_local for row in source_rows), Decimal(0))
        source_cost_base = sum((row.lot_cost_base for row in source_rows), Decimal(0))
        return AverageCostPoolPersistedSummary(
            source_count=source_count,
            source_quantity=source_quantity,
            source_cost_local=source_cost_local,
            source_cost_base=source_cost_base,
            source_lineage_valid=all(_source_row_lineage_is_valid(row) for row in source_rows),
            source_original_quantities=tuple(
                (row.source_transaction_id, row.original_quantity) for row in source_rows
            ),
            pool_quantity=pool.pool_quantity if pool is not None else None,
            pool_cost_local=pool.pool_cost_local if pool is not None else None,
            pool_cost_base=pool.pool_cost_base if pool is not None else None,
            pool_instrument_id=pool.instrument_id if pool is not None else None,
            pool_representative_source_transaction_id=(
                pool.representative_source_transaction_id if pool is not None else None
            ),
            pool_state_version=pool.state_version if pool is not None else None,
            pool_calculation_lineage=(
                calculation_lineage_from_payload(pool.calculation_lineage)
                if pool is not None
                else None
            ),
        )

    async def update_selected_open_lot_states(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        states_by_source_transaction_id: dict[str, OpenLotState],
        transition_evidence: CostBasisStateTransitionEvidence,
    ) -> None:
        """Update selected pool source lots without closing omitted open lots."""
        await self._lot_states.update_selected_open_lot_states(
            portfolio_id=portfolio_id,
            security_id=security_id,
            states_by_source_transaction_id=states_by_source_transaction_id,
            transition_evidence=transition_evidence,
        )

    async def _scale_existing_average_cost_sources(
        self,
        transition: AverageCostPoolTransition,
        *,
        transition_lineage: CalculationLineage,
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
        source_states_before = await self._load_average_cost_source_states(predicates)

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
            await self._refresh_average_cost_source_lineage(
                predicates=predicates,
                source_states_before=source_states_before,
                transition=transition,
                transition_lineage=transition_lineage,
            )
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
        residual_values = (
            after.quantity - allocated_quantity,
            after.cost_local - allocated_cost_local,
            after.cost_base - allocated_cost_base,
        )
        if any(value < Decimal(0) for value in residual_values):
            raise ValueError("Average cost source allocation exceeds the target pool aggregate")
        residual_state = OpenLotState(
            original_quantity=residual_values[0],
            quantity=residual_values[0],
            cost_local=residual_values[1],
            cost_base=residual_values[2],
        )
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
        await self._refresh_average_cost_source_lineage(
            predicates=predicates,
            source_states_before=source_states_before,
            transition=transition,
            transition_lineage=transition_lineage,
        )

    async def _load_average_cost_source_states(
        self,
        predicates: list[Any],
    ) -> dict[str, dict[str, object]]:
        rows = (
            await self._session.execute(
                select(
                    PositionLotState.source_transaction_id,
                    PositionLotState.open_quantity,
                    PositionLotState.lot_cost_local,
                    PositionLotState.lot_cost_base,
                    PositionLotState.calculation_lineage,
                )
                .where(*predicates)
                .order_by(PositionLotState.source_transaction_id)
            )
        ).all()
        return {
            str(source_transaction_id): {
                "cost_base": cost_base,
                "cost_local": cost_local,
                "quantity": quantity,
                "source_transaction_id": source_transaction_id,
                "prior_calculation_lineage": calculation_lineage,
            }
            for source_transaction_id, quantity, cost_local, cost_base, calculation_lineage in rows
        }

    async def _refresh_average_cost_source_lineage(
        self,
        *,
        predicates: list[Any],
        source_states_before: dict[str, dict[str, object]],
        transition: AverageCostPoolTransition,
        transition_lineage: CalculationLineage,
    ) -> None:
        source_rows = (
            (
                await self._session.execute(
                    select(PositionLotState)
                    .where(*predicates)
                    .order_by(PositionLotState.source_transaction_id)
                )
            )
            .scalars()
            .all()
        )
        if len(source_rows) != len(source_states_before):
            raise ValueError("Average cost source membership changed during the locked transition")
        for row in source_rows:
            source_transaction_id = str(row.source_transaction_id)
            state_before = source_states_before.get(source_transaction_id)
            if state_before is None:
                raise ValueError(
                    "Average cost source identity changed during the locked transition"
                )
            prior_lineage = calculation_lineage_from_payload(
                state_before["prior_calculation_lineage"]
            )
            row.calculation_lineage = build_cost_basis_state_lineage(
                algorithm_id="average-cost-source-transition",
                input_payload={
                    "pool_before": _checkpoint_payload(transition.before),
                    "pool_target": _open_lot_state_payload(transition.existing_sources_after),
                    "prior_calculation_lineage": (
                        prior_lineage.lineage_payload() if prior_lineage is not None else None
                    ),
                    "source_before": {
                        key: value
                        for key, value in state_before.items()
                        if key != "prior_calculation_lineage"
                    },
                    "transition_lineage": transition_lineage.lineage_payload(),
                },
                output_payload=lot_state_lineage_output_from_row(row),
            ).lineage_payload()


_SOURCE_STATE_LINEAGE_ALGORITHMS = frozenset(
    {
        "average-cost-source-rebuild",
        "average-cost-source-transition",
        "cost-basis-opening-lot-materialization",
        "cost-basis-complete-lot-snapshot",
        "cost-basis-selected-lot-update",
    }
)


def _source_row_lineage_is_valid(row: Any) -> bool:
    try:
        lineage = calculation_lineage_from_payload(row.calculation_lineage)
    except (TypeError, ValueError):
        return False
    if lineage is None:
        return False
    if (
        lineage.algorithm_id not in _SOURCE_STATE_LINEAGE_ALGORITHMS
        or lineage.algorithm_version != 1
        or lineage.intermediate_precision != COST_BASIS_STATE_LEDGER_OUTPUT_V1.working_precision
        or lineage.numeric_output_policy != COST_BASIS_STATE_LEDGER_OUTPUT_V1.lineage_identity()
    ):
        return False
    return bool(
        calculation_lineage_binds_output(
            lineage,
            output_payload=canonical_cost_basis_output_payload(
                lot_state_lineage_output_from_row(row)
            ),
        )
    )


def _open_lot_state_payload(state: OpenLotState) -> dict[str, object]:
    return {
        "cost_base": state.cost_base,
        "cost_local": state.cost_local,
        "quantity": state.quantity,
    }


def _checkpoint_payload(checkpoint: AverageCostPoolCheckpoint) -> dict[str, object]:
    return {
        "calculation_lineage": (
            checkpoint.calculation_lineage.lineage_payload()
            if checkpoint.calculation_lineage is not None
            else None
        ),
        "cost_base": checkpoint.cost_base,
        "cost_local": checkpoint.cost_local,
        "instrument_id": checkpoint.instrument_id,
        "portfolio_id": checkpoint.portfolio_id,
        "quantity": checkpoint.quantity,
        "representative_source_transaction_id": (checkpoint.representative_source_transaction_id),
        "security_id": checkpoint.security_id,
        "state_version": checkpoint.state_version,
    }
