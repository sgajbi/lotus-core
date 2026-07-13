"""SQLAlchemy adapters for generic simulation state and projection baselines."""

from collections.abc import Sequence
from datetime import date, datetime
from typing import Any, cast

from portfolio_common.database_models import (
    DailyPositionSnapshot,
    Instrument,
    Portfolio,
    PositionHistory,
    PositionState,
)
from portfolio_common.database_models import (
    SimulationChange as SimulationChangeRow,
)
from portfolio_common.database_models import (
    SimulationSession as SimulationSessionRow,
)
from portfolio_common.domain.decimal_amount import decimal_or_none, decimal_or_zero
from portfolio_common.identifiers import normalize_lookup_identifier
from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.simulation import (
    SimulationChange,
    SimulationInstrument,
    SimulationPositionBaseline,
    SimulationSession,
)


class SqlAlchemySimulationStore:
    """Persist simulation state while returning immutable domain records."""

    def __init__(self, db: AsyncSession):
        self._db = db

    async def stage_session(
        self,
        *,
        session_id: str,
        portfolio_id: str,
        created_by: str | None,
        created_at: datetime,
        expires_at: datetime,
    ) -> None:
        self._db.add(
            SimulationSessionRow(
                session_id=session_id,
                portfolio_id=portfolio_id,
                status="ACTIVE",
                version=1,
                created_by=created_by,
                created_at=created_at,
                expires_at=expires_at,
            )
        )

    async def get_session(self, session_id: str) -> SimulationSession | None:
        result = await self._db.execute(
            select(SimulationSessionRow).where(SimulationSessionRow.session_id == session_id)
        )
        row = result.scalars().first()
        return _session_record(row) if row is not None else None

    async def stage_session_close(self, session_id: str, *, version: int) -> None:
        await self._db.execute(
            update(SimulationSessionRow)
            .where(SimulationSessionRow.session_id == session_id)
            .values(status="CLOSED", version=version, updated_at=func.now())
        )

    async def stage_changes(
        self,
        session: SimulationSession,
        *,
        version: int,
        changes: Sequence[dict[str, Any]],
    ) -> None:
        await self._db.execute(
            update(SimulationSessionRow)
            .where(SimulationSessionRow.session_id == session.session_id)
            .values(version=version, updated_at=func.now())
        )
        for item in changes:
            self._db.add(
                SimulationChangeRow(
                    change_id=item["change_id"],
                    session_id=session.session_id,
                    portfolio_id=session.portfolio_id,
                    security_id=item["security_id"],
                    transaction_type=item["transaction_type"],
                    quantity=decimal_or_none(item.get("quantity")),
                    price=decimal_or_none(item.get("price")),
                    amount=decimal_or_none(item.get("amount")),
                    currency=item.get("currency"),
                    effective_date=item.get("effective_date"),
                    change_metadata=item.get("metadata"),
                )
            )

    async def stage_change_delete(
        self,
        session_id: str,
        change_id: str,
        *,
        version: int,
    ) -> bool:
        result = await self._db.execute(
            delete(SimulationChangeRow).where(
                SimulationChangeRow.session_id == session_id,
                SimulationChangeRow.change_id == change_id,
            )
        )
        if int(result.rowcount or 0) == 0:
            return False
        await self._db.execute(
            update(SimulationSessionRow)
            .where(SimulationSessionRow.session_id == session_id)
            .values(version=version, updated_at=func.now())
        )
        return True

    async def get_changes(self, session_id: str) -> list[SimulationChange]:
        result = await self._db.execute(
            select(SimulationChangeRow)
            .where(SimulationChangeRow.session_id == session_id)
            .order_by(SimulationChangeRow.created_at.asc(), SimulationChangeRow.id.asc())
        )
        rows = cast(list[SimulationChangeRow], result.scalars().all())
        return [_change_record(row) for row in rows]


class SqlAlchemySimulationBaselineReader:
    """Read current portfolio positions and instrument enrichment for projection."""

    def __init__(self, db: AsyncSession):
        self._db = db

    async def portfolio_exists(self, portfolio_id: str) -> bool:
        result = await self._db.execute(
            select(Portfolio.portfolio_id).where(Portfolio.portfolio_id == portfolio_id).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def get_current_positions(self, portfolio_id: str) -> list[SimulationPositionBaseline]:
        snapshot_rows = await self._current_snapshot_rows(portfolio_id)
        if snapshot_rows:
            return [
                _snapshot_baseline(snapshot, instrument) for snapshot, instrument in snapshot_rows
            ]
        history_rows = await self._current_history_rows(portfolio_id)
        return [_history_baseline(history, instrument) for history, instrument in history_rows]

    async def get_instruments(self, security_ids: list[str]) -> list[SimulationInstrument]:
        normalized_ids = list(
            dict.fromkeys(
                normalized
                for value in security_ids
                if (normalized := normalize_lookup_identifier(value))
            )
        )
        if not normalized_ids:
            return []
        result = await self._db.execute(
            select(Instrument).where(func.trim(Instrument.security_id).in_(normalized_ids))
        )
        rows = cast(list[Instrument], result.scalars().all())
        return [_instrument_record(row) for row in rows]

    async def _current_snapshot_rows(
        self, portfolio_id: str
    ) -> list[tuple[DailyPositionSnapshot, Instrument]]:
        current_history = _current_position_history_scope(portfolio_id)
        snapshot_security_id = func.trim(DailyPositionSnapshot.security_id)
        ranked_snapshots = (
            select(
                DailyPositionSnapshot.id.label("snapshot_id"),
                func.row_number()
                .over(
                    partition_by=(
                        DailyPositionSnapshot.portfolio_id,
                        snapshot_security_id,
                    ),
                    order_by=(
                        DailyPositionSnapshot.date.desc(),
                        DailyPositionSnapshot.id.desc(),
                    ),
                )
                .label("rn"),
            )
            .join(
                current_history,
                and_(
                    DailyPositionSnapshot.portfolio_id == current_history.c.portfolio_id,
                    snapshot_security_id == current_history.c.security_id,
                    DailyPositionSnapshot.epoch == current_history.c.epoch,
                    DailyPositionSnapshot.quantity == current_history.c.quantity,
                ),
            )
            .where(
                DailyPositionSnapshot.portfolio_id == portfolio_id,
                DailyPositionSnapshot.quantity != 0,
            )
            .subquery()
        )
        result = await self._db.execute(
            select(DailyPositionSnapshot, Instrument)
            .join(
                ranked_snapshots,
                and_(
                    DailyPositionSnapshot.id == ranked_snapshots.c.snapshot_id,
                    ranked_snapshots.c.rn == 1,
                ),
            )
            .join(Instrument, func.trim(Instrument.security_id) == snapshot_security_id)
            .order_by(snapshot_security_id)
        )
        return cast(list[tuple[DailyPositionSnapshot, Instrument]], result.all())

    async def _current_history_rows(
        self, portfolio_id: str
    ) -> list[tuple[PositionHistory, Instrument]]:
        history_security_id = func.trim(PositionHistory.security_id)
        state_security_id = func.trim(PositionState.security_id)
        ranked_history = (
            select(
                PositionHistory.id.label("position_history_id"),
                func.row_number()
                .over(
                    partition_by=history_security_id,
                    order_by=(PositionHistory.position_date.desc(), PositionHistory.id.desc()),
                )
                .label("rn"),
            )
            .join(
                PositionState,
                and_(
                    PositionHistory.portfolio_id == PositionState.portfolio_id,
                    history_security_id == state_security_id,
                    PositionHistory.epoch == PositionState.epoch,
                ),
            )
            .where(PositionHistory.portfolio_id == portfolio_id)
            .subquery()
        )
        result = await self._db.execute(
            select(PositionHistory, Instrument)
            .join(
                ranked_history,
                and_(
                    PositionHistory.id == ranked_history.c.position_history_id,
                    ranked_history.c.rn == 1,
                ),
            )
            .join(Instrument, func.trim(Instrument.security_id) == history_security_id)
            .where(PositionHistory.quantity != 0)
            .order_by(history_security_id)
        )
        return cast(list[tuple[PositionHistory, Instrument]], result.all())


def _current_position_history_scope(portfolio_id: str):
    history_security_id = func.trim(PositionHistory.security_id)
    state_security_id = func.trim(PositionState.security_id)
    ranked_history = (
        select(
            PositionHistory.portfolio_id.label("portfolio_id"),
            history_security_id.label("security_id"),
            PositionHistory.epoch.label("epoch"),
            PositionHistory.quantity.label("quantity"),
            func.row_number()
            .over(
                partition_by=(PositionHistory.portfolio_id, history_security_id),
                order_by=(PositionHistory.position_date.desc(), PositionHistory.id.desc()),
            )
            .label("rn"),
        )
        .join(
            PositionState,
            and_(
                PositionHistory.portfolio_id == PositionState.portfolio_id,
                history_security_id == state_security_id,
                PositionHistory.epoch == PositionState.epoch,
            ),
        )
        .where(PositionHistory.portfolio_id == portfolio_id)
        .subquery()
    )
    return (
        select(ranked_history)
        .where(ranked_history.c.rn == 1, ranked_history.c.quantity != 0)
        .subquery()
    )


def _session_record(row: SimulationSessionRow) -> SimulationSession:
    return SimulationSession(
        session_id=str(row.session_id),
        portfolio_id=str(row.portfolio_id),
        status=str(row.status),
        version=int(row.version),
        created_by=str(row.created_by) if row.created_by is not None else None,
        created_at=cast(datetime, row.created_at),
        expires_at=cast(datetime, row.expires_at),
    )


def _change_record(row: SimulationChangeRow) -> SimulationChange:
    return SimulationChange(
        change_id=str(row.change_id),
        session_id=str(row.session_id),
        portfolio_id=str(row.portfolio_id),
        security_id=str(row.security_id),
        transaction_type=str(row.transaction_type),
        quantity=decimal_or_none(row.quantity),
        price=decimal_or_none(row.price),
        amount=decimal_or_none(row.amount),
        currency=str(row.currency) if row.currency is not None else None,
        effective_date=cast(date | None, row.effective_date),
        metadata=cast(dict[str, Any] | None, row.change_metadata),
        created_at=cast(datetime, row.created_at),
    )


def _snapshot_baseline(
    row: DailyPositionSnapshot,
    instrument: Instrument,
) -> SimulationPositionBaseline:
    return SimulationPositionBaseline(
        security_id=str(row.security_id).strip(),
        position_date=cast(date, row.date),
        quantity=decimal_or_zero(row.quantity),
        cost_basis=decimal_or_none(row.cost_basis),
        cost_basis_local=decimal_or_none(row.cost_basis_local),
        instrument_name=str(instrument.name),
        asset_class=str(instrument.asset_class) if instrument.asset_class is not None else None,
    )


def _history_baseline(
    row: PositionHistory,
    instrument: Instrument,
) -> SimulationPositionBaseline:
    return SimulationPositionBaseline(
        security_id=str(row.security_id).strip(),
        position_date=cast(date, row.position_date),
        quantity=decimal_or_zero(row.quantity),
        cost_basis=decimal_or_none(row.cost_basis),
        cost_basis_local=decimal_or_none(row.cost_basis_local),
        instrument_name=str(instrument.name),
        asset_class=str(instrument.asset_class) if instrument.asset_class is not None else None,
    )


def _instrument_record(row: Instrument) -> SimulationInstrument:
    return SimulationInstrument(
        security_id=str(row.security_id).strip(),
        name=str(row.name),
        asset_class=str(row.asset_class) if row.asset_class is not None else None,
    )
