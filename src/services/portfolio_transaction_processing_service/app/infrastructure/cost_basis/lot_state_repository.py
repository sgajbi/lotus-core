"""SQLAlchemy persistence for cost-basis lot state and disposal checkpoints."""

from decimal import Decimal
from typing import cast

from portfolio_common.database_models import Portfolio, PositionLotState
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    calculation_lineage_from_payload,
)
from portfolio_common.domain.transaction_control_codes import normalize_transaction_control_code
from portfolio_common.identifiers import normalize_lookup_identifier
from portfolio_common.utils import async_timed
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.postgresql.dml import Insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from ...domain.cost_basis import (
    LOT_OPENING_BEHAVIORS,
    AmortizedCostCarryState,
    CostBasisTransaction,
    OpenLotState,
    transaction_lot_behavior,
)
from ...domain.cost_basis.state_lineage import (
    CostBasisStateTransitionEvidence,
    build_cost_basis_state_lineage,
)
from ...ports import OpenLotCheckpointRecord
from ..transaction_mapping.booked_transaction import to_booked_transaction_from_record
from .lot_state_lineage import lot_state_lineage_output_from_row
from .lot_state_mapper import buy_lot_state_payload, mutable_lot_state_fields


class SqlAlchemyCostBasisLotRepository:
    """Persist open lots and load bounded cost-basis checkpoints."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @async_timed(repository="CostBasisLotRepository", method="get_open_lot_checkpoint_records")
    async def get_open_lot_checkpoint_records(
        self,
        *,
        portfolio_id: str,
        security_id: str,
    ) -> list[OpenLotCheckpointRecord]:
        """Load every positive open lot in deterministic acquisition order."""

        statement = self._open_lot_checkpoint_statement(
            portfolio_id=portfolio_id,
            security_id=security_id,
        )
        rows = (await self._session.execute(statement)).all()
        return [self._to_checkpoint_record(lot, transaction) for lot, transaction in rows]

    @async_timed(
        repository="CostBasisLotRepository",
        method="get_fifo_disposal_lot_checkpoint_records",
    )
    async def get_fifo_disposal_lot_checkpoint_records(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        required_quantity: Decimal,
    ) -> list[OpenLotCheckpointRecord]:
        """Stream only the oldest open lots needed to cover one FIFO disposal."""

        if required_quantity <= Decimal(0):
            raise ValueError("FIFO disposal checkpoint quantity must be positive")

        statement = self._open_lot_checkpoint_statement(
            portfolio_id=portfolio_id,
            security_id=security_id,
        ).execution_options(yield_per=64)
        records: list[OpenLotCheckpointRecord] = []
        covered_quantity = Decimal(0)
        result = await self._session.stream(statement)
        try:
            async for lot, transaction in result:
                records.append(self._to_checkpoint_record(lot, transaction))
                covered_quantity += lot.open_quantity
                if covered_quantity >= required_quantity:
                    break
        finally:
            await result.close()
        return records

    @async_timed(repository="CostBasisLotRepository", method="upsert_buy_lot_state")
    async def upsert_buy_lot_state(self, transaction: CostBasisTransaction) -> None:
        """Idempotently persist the lot opened by a purchase transaction."""

        await self._session.execute(buy_lot_state_upsert_statement(transaction))

    async def ensure_acquisition_lot_parent(
        self, transaction: CostBasisTransaction, *, tenant_id: str
    ) -> None:
        """Validate durable source authority, then insert only an absent acquisition lot.

        A conflicting existing lot is never repaired or refreshed here. In particular,
        residual quantity, amortized carry, lineage and audit timestamps remain owned
        by the existing complete/selected lot-state transitions.
        """
        source_tenant_assertion = getattr(transaction, "tenant_id", None)
        if (
            transaction_lot_behavior(transaction.transaction_type) not in LOT_OPENING_BEHAVIORS
            or not transaction.quantity.is_finite()
            or transaction.quantity <= 0
            or not isinstance(tenant_id, str)
            or not tenant_id.strip()
            or (source_tenant_assertion is not None and source_tenant_assertion != tenant_id)
        ):
            raise ValueError("Acquisition lot parent requires an eligible tenant-scoped source")
        source = (
            await self._session.execute(
                select(DBTransaction, Portfolio)
                .join(Portfolio, Portfolio.portfolio_id == DBTransaction.portfolio_id)
                .where(DBTransaction.transaction_id == transaction.transaction_id)
                .with_for_update(of=(DBTransaction, Portfolio))
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        if source is None:
            raise ValueError("Acquisition lot parent requires a durable source transaction")
        source_transaction, portfolio = source
        _require_acquisition_source_identity(transaction, source_transaction, portfolio, tenant_id)

        inserted = await self._session.execute(acquisition_lot_parent_insert_statement(transaction))
        if inserted.scalar_one_or_none() is not None:
            return
        existing = (
            (
                await self._session.execute(
                    select(PositionLotState)
                    .where(
                        or_(
                            PositionLotState.source_transaction_id == transaction.transaction_id,
                            PositionLotState.lot_id == f"LOT-{transaction.transaction_id}",
                        )
                    )
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        if len(existing) != 1 or not _same_acquisition_parent_identity(existing[0], transaction):
            raise ValueError("Acquisition lot parent conflicts with durable source identity")

    @async_timed(repository="CostBasisLotRepository", method="update_open_lot_states")
    async def update_open_lot_states(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        states_by_source_transaction_id: dict[str, OpenLotState],
        transition_evidence: CostBasisStateTransitionEvidence,
    ) -> None:
        """Replace the complete open-lot snapshot for one portfolio-security stream."""

        lot_rows = await self._load_lot_rows(
            portfolio_id=portfolio_id,
            security_id=security_id,
        )
        for lot_row in lot_rows:
            prior_lineage = calculation_lineage_from_payload(lot_row.calculation_lineage)
            state = states_by_source_transaction_id.get(lot_row.source_transaction_id)
            if state is None:
                lot_row.open_quantity = Decimal(0)
                lot_row.lot_cost_local = Decimal(0)
                lot_row.lot_cost_base = Decimal(0)
                _apply_amortized_cost_carry(lot_row, None)
                lot_row.calculation_lineage = _open_lot_state_lineage_payload(
                    lot_row=lot_row,
                    algorithm_id="cost-basis-complete-lot-snapshot",
                    prior_lineage=prior_lineage,
                    transition_evidence=transition_evidence,
                )
                continue
            lot_row.original_quantity = state.original_quantity
            lot_row.open_quantity = state.quantity
            lot_row.lot_cost_local = state.cost_local
            lot_row.lot_cost_base = state.cost_base
            _apply_amortized_cost_carry(lot_row, state.amortized_cost)
            lot_row.calculation_lineage = _open_lot_state_lineage_payload(
                lot_row=lot_row,
                algorithm_id="cost-basis-complete-lot-snapshot",
                prior_lineage=prior_lineage,
                transition_evidence=transition_evidence,
            )

    @async_timed(repository="CostBasisLotRepository", method="update_selected_open_lot_states")
    async def update_selected_open_lot_states(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        states_by_source_transaction_id: dict[str, OpenLotState],
        transition_evidence: CostBasisStateTransitionEvidence,
    ) -> None:
        """Update selected source lots without closing omitted open lots."""

        if not states_by_source_transaction_id:
            return
        source_transaction_ids = set(states_by_source_transaction_id)
        lot_rows = await self._load_lot_rows(
            portfolio_id=portfolio_id,
            security_id=security_id,
            source_transaction_ids=source_transaction_ids,
        )
        persisted_source_ids = {lot_row.source_transaction_id for lot_row in lot_rows}
        missing_source_ids = source_transaction_ids - persisted_source_ids
        if missing_source_ids:
            missing_ids = ", ".join(sorted(missing_source_ids))
            raise ValueError(f"Selected cost-basis source lots are missing: {missing_ids}")

        for lot_row in lot_rows:
            prior_lineage = calculation_lineage_from_payload(lot_row.calculation_lineage)
            state = states_by_source_transaction_id[lot_row.source_transaction_id]
            lot_row.original_quantity = state.original_quantity
            lot_row.open_quantity = state.quantity
            lot_row.lot_cost_local = state.cost_local
            lot_row.lot_cost_base = state.cost_base
            _apply_amortized_cost_carry(lot_row, state.amortized_cost)
            lot_row.calculation_lineage = _open_lot_state_lineage_payload(
                lot_row=lot_row,
                algorithm_id="cost-basis-selected-lot-update",
                prior_lineage=prior_lineage,
                transition_evidence=transition_evidence,
            )

    @staticmethod
    def _open_lot_checkpoint_statement(
        *, portfolio_id: str, security_id: str
    ) -> Select[tuple[PositionLotState, DBTransaction]]:
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        normalized_security_id = normalize_lookup_identifier(security_id)
        return (
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

    async def _load_lot_rows(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        source_transaction_ids: set[str] | None = None,
    ) -> list[PositionLotState]:
        statement = select(PositionLotState).where(
            func.trim(PositionLotState.portfolio_id) == normalize_lookup_identifier(portfolio_id),
            func.trim(PositionLotState.security_id) == normalize_lookup_identifier(security_id),
        )
        if source_transaction_ids is not None:
            statement = statement.where(
                PositionLotState.source_transaction_id.in_(source_transaction_ids)
            )
        return list((await self._session.execute(statement)).scalars().all())

    @staticmethod
    def _to_checkpoint_record(
        lot: PositionLotState,
        transaction: DBTransaction,
    ) -> OpenLotCheckpointRecord:
        return OpenLotCheckpointRecord(
            transaction=to_booked_transaction_from_record(transaction),
            original_quantity=lot.original_quantity,
            quantity=lot.open_quantity,
            cost_local=lot.lot_cost_local,
            cost_base=lot.lot_cost_base,
            amortized_cost=_amortized_cost_carry(lot),
        )


def buy_lot_state_upsert_statement(transaction: CostBasisTransaction) -> Insert:
    """Build the canonical idempotent opening-lot write."""

    statement = pg_insert(PositionLotState).values(**buy_lot_state_payload(transaction))
    return statement.on_conflict_do_update(
        index_elements=["source_transaction_id"],
        set_=mutable_lot_state_fields(statement),
    )


def acquisition_lot_parent_insert_statement(transaction: CostBasisTransaction) -> Insert:
    """Use canonical opening-lot payload and refuse to overwrite any unique identity."""
    return (
        pg_insert(PositionLotState)
        .values(**buy_lot_state_payload(transaction))
        .on_conflict_do_nothing()
        .returning(PositionLotState.lot_id)
    )


def _require_acquisition_source_identity(
    candidate: CostBasisTransaction,
    source: DBTransaction,
    portfolio: Portfolio,
    tenant_id: str,
) -> None:
    if (
        portfolio.tenant_id != tenant_id
        or source.portfolio_id != candidate.portfolio_id
        or source.security_id != candidate.security_id
        or source.instrument_id != candidate.instrument_id
        or source.transaction_date != candidate.transaction_date
        or source.quantity != candidate.quantity
        or normalize_transaction_control_code(source.transaction_type)
        != normalize_transaction_control_code(candidate.transaction_type)
    ):
        raise ValueError("Acquisition lot parent conflicts with durable source scope")


def _same_acquisition_parent_identity(
    lot: PositionLotState, transaction: CostBasisTransaction
) -> bool:
    return bool(
        lot.lot_id == f"LOT-{transaction.transaction_id}"
        and lot.source_transaction_id == transaction.transaction_id
        and lot.portfolio_id == transaction.portfolio_id
        and lot.security_id == transaction.security_id
        and lot.instrument_id == transaction.instrument_id
        and lot.acquisition_date == transaction.transaction_date.date()
    )


def _amortized_cost_carry(lot: PositionLotState) -> AmortizedCostCarryState | None:
    values = (
        lot.amortized_cost_profile_id,
        lot.amortized_cost_profile_version,
        lot.amortized_cost_profile_content_hash,
        lot.amortized_cost_recognized_through,
        lot.amortized_cost_scheduled_local,
        lot.amortized_book_carrying_local,
        lot.amortized_book_carrying_base,
        lot.amortized_cost_book_fx_rate_to_base,
    )
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise ValueError("persisted lot has partial amortized-cost carry state")
    return AmortizedCostCarryState(
        profile_id=str(lot.amortized_cost_profile_id),
        profile_version=int(lot.amortized_cost_profile_version),
        profile_content_hash=str(lot.amortized_cost_profile_content_hash),
        recognized_through_date=lot.amortized_cost_recognized_through,
        scheduled_cost_local=lot.amortized_cost_scheduled_local,
        carrying_amount_local=lot.amortized_book_carrying_local,
        carrying_amount_base=lot.amortized_book_carrying_base,
        book_cost_fx_rate_to_base=lot.amortized_cost_book_fx_rate_to_base,
    )


def _apply_amortized_cost_carry(
    lot: PositionLotState,
    carry: AmortizedCostCarryState | None,
) -> None:
    lot.amortized_cost_profile_id = carry.profile_id if carry is not None else None
    lot.amortized_cost_profile_version = carry.profile_version if carry is not None else None
    lot.amortized_cost_profile_content_hash = (
        carry.profile_content_hash if carry is not None else None
    )
    lot.amortized_cost_recognized_through = (
        carry.recognized_through_date if carry is not None else None
    )
    lot.amortized_cost_scheduled_local = carry.scheduled_cost_local if carry is not None else None
    lot.amortized_book_carrying_local = carry.carrying_amount_local if carry is not None else None
    lot.amortized_book_carrying_base = carry.carrying_amount_base if carry is not None else None
    lot.amortized_cost_book_fx_rate_to_base = (
        carry.book_cost_fx_rate_to_base if carry is not None else None
    )


def _open_lot_state_lineage_payload(
    *,
    lot_row: PositionLotState,
    algorithm_id: str,
    prior_lineage: CalculationLineage | None,
    transition_evidence: CostBasisStateTransitionEvidence,
) -> dict[str, object]:
    lineage: CalculationLineage = build_cost_basis_state_lineage(
        algorithm_id=algorithm_id,
        input_payload={
            "prior_calculation_lineage": (
                prior_lineage.lineage_payload() if prior_lineage is not None else None
            ),
            "transition": transition_evidence.lineage_payload(),
        },
        output_payload=lot_state_lineage_output_from_row(lot_row),
    )
    return cast(dict[str, object], lineage.lineage_payload())
