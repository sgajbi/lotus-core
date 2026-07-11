# services/calculators/cost_calculator_service/app/repository.py
import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass, fields
from datetime import date
from decimal import Decimal
from time import monotonic
from typing import Any, List, Optional, cast

from portfolio_common.currency_codes import normalize_currency_code
from portfolio_common.database_models import (
    AccruedIncomeOffsetState,
    AverageCostPoolState,
    CostBasisProcessingState,
    FinancialReconciliationFinding,
    FinancialReconciliationRun,
    FxRate,
    Instrument,
    Portfolio,
    PositionLotState,
    TransactionCost,
)
from portfolio_common.database_models import (
    Transaction as DBTransaction,
)
from portfolio_common.events import TransactionEvent, event_business_payload
from portfolio_common.identifiers import normalize_lookup_identifier
from portfolio_common.monitoring import observe_cost_basis_processing_lock_wait
from portfolio_common.utils import async_timed
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    CostBasisTransaction as EngineTransaction,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    EffectiveFxRate,
    OpenLotState,
)

from .average_cost_pool_checkpoint import (
    AverageCostPoolCheckpoint,
    AverageCostPoolRebuildPlan,
    AverageCostPoolTransition,
)
from .cost_processing_checkpoint import CostBasisProcessingCheckpoint

logger = logging.getLogger(__name__)


def _cost_basis_processing_lock_key(portfolio_id: str, security_id: str) -> int:
    normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
    normalized_security_id = normalize_lookup_identifier(security_id)
    lock_scope = f"cost-basis-processing:{normalized_portfolio_id}:{normalized_security_id}"
    digest = hashlib.blake2b(lock_scope.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, byteorder="big", signed=True)


TRANSACTION_METADATA_FIELDS = (
    "economic_event_id",
    "linked_transaction_group_id",
    "calculation_policy_id",
    "calculation_policy_version",
    "source_system",
    "cash_entry_mode",
    "external_cash_transaction_id",
    "settlement_cash_account_id",
    "settlement_cash_instrument_id",
    "movement_direction",
    "originating_transaction_id",
    "originating_transaction_type",
    "adjustment_reason",
    "link_type",
    "reconciliation_key",
    "interest_direction",
    "withholding_tax_amount",
    "other_interest_deductions_amount",
    "net_interest_amount",
    "component_type",
    "component_id",
    "linked_component_ids",
    "fx_cash_leg_role",
    "linked_fx_cash_leg_id",
    "settlement_status",
    "pair_base_currency",
    "pair_quote_currency",
    "fx_rate_quote_convention",
    "buy_currency",
    "sell_currency",
    "buy_amount",
    "sell_amount",
    "contract_rate",
    "fx_contract_id",
    "fx_contract_open_transaction_id",
    "fx_contract_close_transaction_id",
    "settlement_of_fx_contract_id",
    "swap_event_id",
    "near_leg_group_id",
    "far_leg_group_id",
    "spot_exposure_model",
    "fx_realized_pnl_mode",
    "allocated_cost_basis_local",
    "allocated_cost_basis_base",
    "realized_capital_pnl_local",
    "realized_fx_pnl_local",
    "realized_total_pnl_local",
    "realized_capital_pnl_base",
    "realized_fx_pnl_base",
    "realized_total_pnl_base",
    "parent_transaction_reference",
    "linked_parent_event_id",
    "parent_event_reference",
    "child_role",
    "child_sequence_hint",
    "dependency_reference_ids",
    "source_instrument_id",
    "target_instrument_id",
    "source_transaction_reference",
    "target_transaction_reference",
    "linked_cash_transaction_id",
    "has_synthetic_flow",
    "synthetic_flow_effective_date",
    "synthetic_flow_amount_local",
    "synthetic_flow_currency",
    "synthetic_flow_amount_base",
    "synthetic_flow_fx_rate_to_base",
    "synthetic_flow_price_used",
    "synthetic_flow_quantity_used",
    "synthetic_flow_valuation_method",
    "synthetic_flow_classification",
    "synthetic_flow_price_source",
    "synthetic_flow_fx_source",
    "synthetic_flow_source",
)

TRANSACTION_TABLE_FIELDS = frozenset(DBTransaction.__table__.columns.keys())
TRANSACTION_EVENT_PERSISTENCE_EXCLUDE_FIELDS = frozenset(
    {"id", "epoch", "brokerage", "stamp_duty", "exchange_fee", "gst", "other_fees"}
)


def _transaction_event_payload(event: TransactionEvent) -> dict[str, Any]:
    event_payload = event_business_payload(event, mode="python")
    return {
        field: value
        for field, value in event_payload.items()
        if value is not None
        and field in TRANSACTION_TABLE_FIELDS
        and field not in TRANSACTION_EVENT_PERSISTENCE_EXCLUDE_FIELDS
    }


FEE_COMPONENT_FIELDS = (
    "brokerage",
    "stamp_duty",
    "exchange_fee",
    "gst",
    "other_fees",
)


@dataclass(frozen=True, slots=True)
class OpenLotCheckpointRecord:
    transaction: DBTransaction
    quantity: Decimal
    cost_local: Decimal
    cost_base: Decimal


@dataclass(frozen=True, slots=True)
class AverageCostPoolCheckpointRecord:
    checkpoint: AverageCostPoolCheckpoint
    representative_transaction: DBTransaction | None


@dataclass(frozen=True, slots=True)
class AverageCostPoolPersistedSummary:
    source_count: int
    source_quantity: Decimal
    source_cost_local: Decimal
    source_cost_base: Decimal
    pool_quantity: Decimal | None
    pool_cost_local: Decimal | None
    pool_cost_base: Decimal | None


def _positive_fee_components(fees: object | None) -> dict[str, Decimal]:
    if fees is None:
        return {}
    return {
        field_name: amount
        for field_name in FEE_COMPONENT_FIELDS
        if (amount := getattr(fees, field_name, None) or Decimal(0)) > 0
    }


def _transaction_cost_rows(
    *,
    transaction_result: EngineTransaction,
    db_txn: DBTransaction,
) -> list[TransactionCost]:
    currency = normalize_currency_code(db_txn.trade_currency or db_txn.currency)
    return [
        TransactionCost(
            transaction_id=transaction_result.transaction_id,
            fee_type=fee_type,
            amount=amount,
            currency=currency,
        )
        for fee_type, amount in _positive_fee_components(transaction_result.fees).items()
    ]


def _buy_lot_payload(transaction_result: EngineTransaction) -> dict[str, object]:
    accrued_interest_local = getattr(transaction_result, "accrued_interest", None) or Decimal(0)
    return {
        "lot_id": f"LOT-{transaction_result.transaction_id}",
        "source_transaction_id": transaction_result.transaction_id,
        "portfolio_id": transaction_result.portfolio_id,
        "instrument_id": transaction_result.instrument_id,
        "security_id": transaction_result.security_id,
        "acquisition_date": transaction_result.transaction_date.date(),
        "original_quantity": transaction_result.quantity,
        "open_quantity": transaction_result.quantity,
        "lot_cost_local": transaction_result.net_cost_local or Decimal(0),
        "lot_cost_base": transaction_result.net_cost or Decimal(0),
        "accrued_interest_paid_local": accrued_interest_local,
        "economic_event_id": getattr(transaction_result, "economic_event_id", None),
        "linked_transaction_group_id": getattr(
            transaction_result, "linked_transaction_group_id", None
        ),
        "calculation_policy_id": getattr(transaction_result, "calculation_policy_id", None),
        "calculation_policy_version": getattr(
            transaction_result, "calculation_policy_version", None
        ),
        "source_system": getattr(transaction_result, "source_system", None),
    }


def _excluded_update_fields(insert_stmt: Any, immutable_fields: set[str]) -> dict[str, object]:
    return {c.name: c for c in insert_stmt.excluded if c.name not in immutable_fields}


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


class CostCalculatorRepository:
    AVERAGE_COST_REBUILD_UPSERT_CHUNK_SIZE = 500

    def __init__(self, db: AsyncSession, *, clock: Callable[[], float] = monotonic):
        self.db = db
        self._clock = clock

    @async_timed(repository="CostCalculatorRepository", method="acquire_cost_basis_processing_lock")
    async def acquire_cost_basis_processing_lock(
        self,
        portfolio_id: str,
        security_id: str,
    ) -> None:
        """Serialize cost-basis state transitions for one portfolio/security key."""
        lock_key = _cost_basis_processing_lock_key(portfolio_id, security_id)
        started_at = self._clock()
        try:
            await self.db.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)").bindparams(lock_key=lock_key)
            )
        except BaseException:
            wait_seconds = max(0.0, self._clock() - started_at)
            observe_cost_basis_processing_lock_wait(
                outcome="failed",
                seconds=wait_seconds,
            )
            logger.warning(
                "Cost-basis processing lock acquisition failed.",
                extra={
                    "portfolio_id": normalize_lookup_identifier(portfolio_id),
                    "security_id": normalize_lookup_identifier(security_id),
                    "lock_wait_seconds": wait_seconds,
                },
                exc_info=True,
            )
            raise
        wait_seconds = max(0.0, self._clock() - started_at)
        observe_cost_basis_processing_lock_wait(
            outcome="acquired",
            seconds=wait_seconds,
        )
        logger.info(
            "Cost-basis processing lock acquired.",
            extra={
                "portfolio_id": normalize_lookup_identifier(portfolio_id),
                "security_id": normalize_lookup_identifier(security_id),
                "lock_wait_seconds": wait_seconds,
            },
        )

    async def get_portfolio(self, portfolio_id: str) -> Optional[Portfolio]:
        """Fetches a portfolio by its portfolio_id string."""
        stmt = select(Portfolio).where(Portfolio.portfolio_id == portfolio_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_instrument(self, security_id: str) -> Optional[Instrument]:
        normalized_security_id = normalize_lookup_identifier(security_id)
        stmt = select(Instrument).where(func.trim(Instrument.security_id) == normalized_security_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_fx_rate_window(
        self,
        from_currency: str,
        to_currency: str,
        *,
        start_date: date,
        end_date: date,
    ) -> list[EffectiveFxRate]:
        """Fetch the effective-rate seed and all pair rates inside a date window."""
        if start_date > end_date:
            raise ValueError("FX rate window start_date must be on or before end_date")

        normalized_from_currency = normalize_currency_code(from_currency)
        normalized_to_currency = normalize_currency_code(to_currency)
        from_currency_expr = func.upper(func.trim(FxRate.from_currency))
        to_currency_expr = func.upper(func.trim(FxRate.to_currency))
        prior_rate = aliased(FxRate)
        prior_rate_date = (
            select(func.max(prior_rate.rate_date))
            .where(
                func.upper(func.trim(prior_rate.from_currency)) == normalized_from_currency,
                func.upper(func.trim(prior_rate.to_currency)) == normalized_to_currency,
                prior_rate.rate_date < start_date,
            )
            .scalar_subquery()
        )
        stmt = (
            select(FxRate)
            .where(
                from_currency_expr == normalized_from_currency,
                to_currency_expr == normalized_to_currency,
                FxRate.rate_date <= end_date,
                or_(
                    FxRate.rate_date >= start_date,
                    FxRate.rate_date == prior_rate_date,
                ),
            )
            .order_by(FxRate.rate_date.asc())
        )
        result = await self.db.execute(stmt)
        return [
            EffectiveFxRate(effective_date=row.rate_date, rate=row.rate)
            for row in result.scalars().all()
        ]

    async def get_transaction_history(
        self, portfolio_id: str, security_id: str, exclude_id: Optional[str] = None
    ) -> List[DBTransaction]:
        """
        Fetches all transactions for a given security in a portfolio,
        optionally excluding one by its transaction_id.
        """
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        normalized_security_id = normalize_lookup_identifier(security_id)
        stmt = select(DBTransaction).where(
            func.trim(DBTransaction.portfolio_id) == normalized_portfolio_id,
            func.trim(DBTransaction.security_id) == normalized_security_id,
        )

        if exclude_id:
            normalized_exclude_id = normalize_lookup_identifier(exclude_id)
            stmt = stmt.where(func.trim(DBTransaction.transaction_id) != normalized_exclude_id)

        stmt = stmt.order_by(
            DBTransaction.transaction_date.asc(),
            DBTransaction.transaction_id.asc(),
        )

        result = await self.db.execute(stmt)
        return cast(List[DBTransaction], result.scalars().all())

    async def get_cost_basis_processing_checkpoint(
        self, *, portfolio_id: str, security_id: str
    ) -> CostBasisProcessingCheckpoint | None:
        stmt = select(CostBasisProcessingState).where(
            CostBasisProcessingState.portfolio_id == normalize_lookup_identifier(portfolio_id),
            CostBasisProcessingState.security_id == normalize_lookup_identifier(security_id),
        )
        row = (await self.db.execute(stmt)).scalars().first()
        if row is None:
            return None
        return CostBasisProcessingCheckpoint(
            portfolio_id=row.portfolio_id,
            security_id=row.security_id,
            cost_basis_method=row.cost_basis_method,
            latest_transaction_date=row.latest_transaction_date,
            latest_dependency_rank=row.latest_dependency_rank,
            latest_cash_dependency_rank=row.latest_cash_dependency_rank,
            latest_child_sequence=row.latest_child_sequence,
            latest_target_instrument_id=row.latest_target_instrument_id,
            latest_quantity=row.latest_quantity,
            latest_transaction_id=row.latest_transaction_id,
            engine_state_version=row.engine_state_version,
        )

    async def upsert_cost_basis_processing_checkpoint(
        self, checkpoint: CostBasisProcessingCheckpoint
    ) -> None:
        payload = {field.name: getattr(checkpoint, field.name) for field in fields(checkpoint)}
        stmt = pg_insert(CostBasisProcessingState).values(**payload)
        await self.db.execute(
            stmt.on_conflict_do_update(
                index_elements=["portfolio_id", "security_id"],
                set_={
                    field_name: getattr(stmt.excluded, field_name)
                    for field_name in payload
                    if field_name not in {"portfolio_id", "security_id"}
                },
            )
        )

    async def get_average_cost_pool_checkpoint_record(
        self,
        *,
        portfolio_id: str,
        security_id: str,
    ) -> AverageCostPoolCheckpointRecord | None:
        stmt = (
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
        row = (await self.db.execute(stmt)).first()
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
            representative_transaction=representative_transaction,
        )

    async def upsert_average_cost_pool_checkpoint(
        self,
        checkpoint: AverageCostPoolCheckpoint,
    ) -> None:
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
        stmt = pg_insert(AverageCostPoolState).values(**payload)
        await self.db.execute(
            stmt.on_conflict_do_update(
                index_elements=["portfolio_id", "security_id"],
                set_={
                    field_name: getattr(stmt.excluded, field_name)
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
        checkpoint = plan.checkpoint
        normalized_portfolio_id = normalize_lookup_identifier(checkpoint.portfolio_id)
        normalized_security_id = normalize_lookup_identifier(checkpoint.security_id)
        await self.db.execute(
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
            payload = _buy_lot_payload(source_transaction)
            state = plan.source_states.get(source_transaction.transaction_id)
            payload.update(
                open_quantity=state.quantity if state is not None else Decimal(0),
                lot_cost_local=state.cost_local if state is not None else Decimal(0),
                lot_cost_base=state.cost_base if state is not None else Decimal(0),
            )
            payloads.append(payload)
        for offset in range(0, len(payloads), self.AVERAGE_COST_REBUILD_UPSERT_CHUNK_SIZE):
            stmt = pg_insert(PositionLotState).values(
                payloads[offset : offset + self.AVERAGE_COST_REBUILD_UPSERT_CHUNK_SIZE]
            )
            await self.db.execute(
                stmt.on_conflict_do_update(
                    index_elements=["source_transaction_id"],
                    set_=_excluded_update_fields(
                        stmt,
                        {"id", "lot_id", "source_transaction_id"},
                    ),
                )
            )

        await self.upsert_average_cost_pool_checkpoint(checkpoint)
        await self.upsert_cost_basis_processing_checkpoint(plan.processing_checkpoint)

    async def get_average_cost_pool_persisted_summary(
        self,
        *,
        portfolio_id: str,
        security_id: str,
    ) -> AverageCostPoolPersistedSummary:
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        normalized_security_id = normalize_lookup_identifier(security_id)
        pool = (
            (
                await self.db.execute(
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
            await self.db.execute(
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
            result = await self.db.execute(
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
        await self.db.execute(
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
            await self.db.execute(
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
        residual_result = await self.db.execute(
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

    async def get_open_lot_checkpoint_records(
        self, *, portfolio_id: str, security_id: str
    ) -> list[OpenLotCheckpointRecord]:
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        normalized_security_id = normalize_lookup_identifier(security_id)
        stmt = (
            select(PositionLotState, DBTransaction)
            .join(
                DBTransaction,
                DBTransaction.transaction_id == PositionLotState.source_transaction_id,
            )
            .where(
                func.trim(PositionLotState.portfolio_id) == normalized_portfolio_id,
                func.trim(PositionLotState.security_id) == normalized_security_id,
                func.trim(DBTransaction.portfolio_id) == normalized_portfolio_id,
                func.trim(DBTransaction.security_id) == normalized_security_id,
                PositionLotState.open_quantity > Decimal(0),
            )
            .order_by(
                DBTransaction.transaction_date.asc(),
                DBTransaction.quantity.desc(),
                DBTransaction.transaction_id.asc(),
            )
        )
        rows = (await self.db.execute(stmt)).all()
        return [
            OpenLotCheckpointRecord(
                transaction=transaction,
                quantity=lot.open_quantity,
                cost_local=lot.lot_cost_local,
                cost_base=lot.lot_cost_base,
            )
            for lot, transaction in rows
        ]

    async def get_fifo_disposal_lot_checkpoint_records(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        required_quantity: Decimal,
    ) -> list[OpenLotCheckpointRecord]:
        """Stream the oldest open lots needed to cover one FIFO disposal."""
        if required_quantity <= Decimal(0):
            raise ValueError("FIFO disposal checkpoint quantity must be positive")

        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        normalized_security_id = normalize_lookup_identifier(security_id)
        stmt = (
            select(PositionLotState, DBTransaction)
            .join(
                DBTransaction,
                DBTransaction.transaction_id == PositionLotState.source_transaction_id,
            )
            .where(
                func.trim(PositionLotState.portfolio_id) == normalized_portfolio_id,
                func.trim(PositionLotState.security_id) == normalized_security_id,
                func.trim(DBTransaction.portfolio_id) == normalized_portfolio_id,
                func.trim(DBTransaction.security_id) == normalized_security_id,
                PositionLotState.open_quantity > Decimal(0),
            )
            .order_by(
                DBTransaction.transaction_date.asc(),
                DBTransaction.quantity.desc(),
                DBTransaction.transaction_id.asc(),
            )
            .execution_options(yield_per=64)
        )

        records: list[OpenLotCheckpointRecord] = []
        covered_quantity = Decimal(0)
        result = await self.db.stream(stmt)
        try:
            async for lot, transaction in result:
                records.append(
                    OpenLotCheckpointRecord(
                        transaction=transaction,
                        quantity=lot.open_quantity,
                        cost_local=lot.lot_cost_local,
                        cost_base=lot.lot_cost_base,
                    )
                )
                covered_quantity += lot.open_quantity
                if covered_quantity >= required_quantity:
                    break
        finally:
            await result.close()
        return records

    async def update_transaction_costs(
        self, transaction_result: EngineTransaction
    ) -> DBTransaction | None:
        """Finds a transaction by its ID and updates its calculated cost fields."""
        stmt = select(DBTransaction).filter_by(transaction_id=transaction_result.transaction_id)
        result = await self.db.execute(stmt)
        db_txn_to_update = result.scalars().first()

        if db_txn_to_update:
            db_txn_to_update.net_cost = transaction_result.net_cost
            db_txn_to_update.gross_cost = transaction_result.gross_cost
            db_txn_to_update.realized_gain_loss = transaction_result.realized_gain_loss
            db_txn_to_update.transaction_fx_rate = transaction_result.transaction_fx_rate
            db_txn_to_update.net_cost_local = transaction_result.net_cost_local
            db_txn_to_update.realized_gain_loss_local = transaction_result.realized_gain_loss_local
            for field_name in TRANSACTION_METADATA_FIELDS:
                field_value = getattr(transaction_result, field_name, None)
                if field_value is not None:
                    setattr(db_txn_to_update, field_name, field_value)

        return db_txn_to_update

    async def get_transaction_by_id(
        self, transaction_id: str, *, portfolio_id: str | None = None
    ) -> DBTransaction | None:
        stmt = select(DBTransaction).where(DBTransaction.transaction_id == transaction_id)
        if portfolio_id:
            stmt = stmt.where(DBTransaction.portfolio_id == portfolio_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_bundle_a_group_transactions(
        self, *, portfolio_id: str, linked_transaction_group_id: str, parent_event_reference: str
    ) -> List[DBTransaction]:
        stmt = (
            select(DBTransaction)
            .where(DBTransaction.portfolio_id == portfolio_id)
            .where(DBTransaction.linked_transaction_group_id == linked_transaction_group_id)
            .where(DBTransaction.parent_event_reference == parent_event_reference)
            .where(
                DBTransaction.transaction_type.in_(
                    ("SPIN_OFF", "SPIN_IN", "DEMERGER_OUT", "DEMERGER_IN", "CASH_CONSIDERATION")
                )
            )
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def record_bundle_a_reconciliation_evidence(
        self,
        *,
        run: dict[str, object],
        findings: list[dict[str, object]],
    ) -> None:
        run_stmt = pg_insert(FinancialReconciliationRun).values(**run)
        await self.db.execute(
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
        for finding in findings:
            finding_stmt = pg_insert(FinancialReconciliationFinding).values(**finding)
            await self.db.execute(
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

    async def create_or_update_transaction_event(self, event: TransactionEvent) -> DBTransaction:
        event_dict = _transaction_event_payload(event)
        stmt = pg_insert(DBTransaction).values(**event_dict)
        update_fields = [k for k in event_dict.keys() if k not in {"id", "transaction_id"}]
        update_dict = {field: getattr(stmt.excluded, field) for field in update_fields}
        await self.db.execute(
            stmt.on_conflict_do_update(index_elements=["transaction_id"], set_=update_dict)
        )
        return DBTransaction(**event_dict)

    async def replace_transaction_cost_breakdown(
        self, transaction_result: EngineTransaction
    ) -> None:
        """
        Replaces the per-fee breakdown rows for a transaction.

        The method is idempotent for reprocessing because existing rows are deleted
        before re-insert using the latest computed fee components.
        """
        stmt = select(DBTransaction).filter_by(transaction_id=transaction_result.transaction_id)
        result = await self.db.execute(stmt)
        db_txn = result.scalars().first()
        if not db_txn:
            return

        await self.db.execute(
            TransactionCost.__table__.delete().where(
                TransactionCost.transaction_id == transaction_result.transaction_id
            )
        )

        self.db.add_all(
            _transaction_cost_rows(transaction_result=transaction_result, db_txn=db_txn)
        )

    async def upsert_buy_lot_state(self, transaction_result: EngineTransaction) -> None:
        """Persists BUY lot state as a durable, idempotent record."""
        stmt = pg_insert(PositionLotState).values(**_buy_lot_payload(transaction_result))
        update_dict = _excluded_update_fields(stmt, {"id", "lot_id", "source_transaction_id"})
        await self.db.execute(
            stmt.on_conflict_do_update(index_elements=["source_transaction_id"], set_=update_dict)
        )

    async def update_open_lot_states(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        states_by_source_transaction_id: dict[str, OpenLotState],
    ) -> None:
        """Reconciles persisted quantity and cost with the latest engine-derived lot state."""
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        normalized_security_id = normalize_lookup_identifier(security_id)
        stmt = select(PositionLotState).where(
            func.trim(PositionLotState.portfolio_id) == normalized_portfolio_id,
            func.trim(PositionLotState.security_id) == normalized_security_id,
        )
        lot_rows = (await self.db.execute(stmt)).scalars().all()
        for lot_row in lot_rows:
            state = states_by_source_transaction_id.get(lot_row.source_transaction_id)
            if state is None:
                lot_row.open_quantity = Decimal(0)
                lot_row.lot_cost_local = Decimal(0)
                lot_row.lot_cost_base = Decimal(0)
                continue
            lot_row.open_quantity = state.quantity
            lot_row.lot_cost_local = state.cost_local
            lot_row.lot_cost_base = state.cost_base

    async def update_selected_open_lot_states(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        states_by_source_transaction_id: dict[str, OpenLotState],
    ) -> None:
        """Update an explicitly selected lot subset without closing omitted open lots."""
        if not states_by_source_transaction_id:
            return

        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        normalized_security_id = normalize_lookup_identifier(security_id)
        source_transaction_ids = set(states_by_source_transaction_id)
        stmt = select(PositionLotState).where(
            func.trim(PositionLotState.portfolio_id) == normalized_portfolio_id,
            func.trim(PositionLotState.security_id) == normalized_security_id,
            PositionLotState.source_transaction_id.in_(source_transaction_ids),
        )
        lot_rows = (await self.db.execute(stmt)).scalars().all()
        persisted_source_ids = {lot_row.source_transaction_id for lot_row in lot_rows}
        missing_source_ids = source_transaction_ids - persisted_source_ids
        if missing_source_ids:
            missing_ids = ", ".join(sorted(missing_source_ids))
            raise ValueError(f"Selected cost-basis source lots are missing: {missing_ids}")

        for lot_row in lot_rows:
            state = states_by_source_transaction_id[lot_row.source_transaction_id]
            lot_row.open_quantity = state.quantity
            lot_row.lot_cost_local = state.cost_local
            lot_row.lot_cost_base = state.cost_base

    async def upsert_accrued_income_offset_state(
        self, transaction_result: EngineTransaction
    ) -> None:
        """Initializes or updates accrued-income offset state for BUY transactions."""
        accrued_interest_local = getattr(transaction_result, "accrued_interest", None) or Decimal(0)
        payload = {
            "offset_id": f"AIO-{transaction_result.transaction_id}",
            "source_transaction_id": transaction_result.transaction_id,
            "portfolio_id": transaction_result.portfolio_id,
            "instrument_id": transaction_result.instrument_id,
            "security_id": transaction_result.security_id,
            "accrued_interest_paid_local": accrued_interest_local,
            "remaining_offset_local": accrued_interest_local,
            "economic_event_id": getattr(transaction_result, "economic_event_id", None),
            "linked_transaction_group_id": getattr(
                transaction_result, "linked_transaction_group_id", None
            ),
            "calculation_policy_id": getattr(transaction_result, "calculation_policy_id", None),
            "calculation_policy_version": getattr(
                transaction_result, "calculation_policy_version", None
            ),
            "source_system": getattr(transaction_result, "source_system", None),
        }
        stmt = pg_insert(AccruedIncomeOffsetState).values(**payload)
        update_dict = {
            c.name: c
            for c in stmt.excluded
            if c.name not in ["id", "offset_id", "source_transaction_id"]
        }
        await self.db.execute(
            stmt.on_conflict_do_update(index_elements=["source_transaction_id"], set_=update_dict)
        )
