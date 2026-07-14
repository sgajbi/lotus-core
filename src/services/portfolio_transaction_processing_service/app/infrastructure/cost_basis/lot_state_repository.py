"""SQLAlchemy persistence for cost-basis lot state and disposal checkpoints."""

from decimal import Decimal

from portfolio_common.database_models import PositionLotState
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent
from portfolio_common.identifiers import normalize_lookup_identifier
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from ...domain.cost_basis import CostBasisTransaction, OpenLotState
from ...ports import OpenLotCheckpointRecord
from ..transaction_mapping.booked_transaction import to_booked_transaction
from .lot_state_mapper import buy_lot_state_payload, mutable_lot_state_fields


class SqlAlchemyCostBasisLotRepository:
    """Persist open lots and load bounded cost-basis checkpoints."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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

    async def upsert_buy_lot_state(self, transaction: CostBasisTransaction) -> None:
        """Idempotently persist the lot opened by a purchase transaction."""

        statement = pg_insert(PositionLotState).values(**buy_lot_state_payload(transaction))
        await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=["source_transaction_id"],
                set_=mutable_lot_state_fields(statement),
            )
        )

    async def update_open_lot_states(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        states_by_source_transaction_id: dict[str, OpenLotState],
    ) -> None:
        """Replace the complete open-lot snapshot for one portfolio-security stream."""

        lot_rows = await self._load_lot_rows(
            portfolio_id=portfolio_id,
            security_id=security_id,
        )
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
            state = states_by_source_transaction_id[lot_row.source_transaction_id]
            lot_row.open_quantity = state.quantity
            lot_row.lot_cost_local = state.cost_local
            lot_row.lot_cost_base = state.cost_base

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
            transaction=to_booked_transaction(TransactionEvent.model_validate(transaction)),
            quantity=lot.open_quantity,
            cost_local=lot.lot_cost_local,
            cost_base=lot.lot_cost_base,
        )
