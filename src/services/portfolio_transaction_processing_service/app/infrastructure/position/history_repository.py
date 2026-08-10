"""Persist position history while keeping SQLAlchemy rows behind a domain port."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from dataclasses import MISSING, fields
from datetime import date, datetime, time
from decimal import Decimal
from time import monotonic
from typing import Any, cast

from portfolio_common.database_models import DailyPositionSnapshot, PositionHistory, Transaction
from portfolio_common.domain.calculation_lineage import calculation_lineage_from_payload
from portfolio_common.identifiers import normalize_lookup_identifier
from portfolio_common.monitoring import observe_position_history_replay_lock_wait
from portfolio_common.utils import async_timed
from sqlalchemy import delete, func, select, text, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ...domain.position.history import PositionHistoryRecord
from ...domain.transaction.booked import BookedTransaction
from ...ports.position_history import PositionMaterializationProgress, PositionReplayWindow

logger = logging.getLogger(__name__)

_TUPLE_FIELDS = frozenset({"linked_component_ids", "dependency_reference_ids"})


def _position_history_replay_lock_key(portfolio_id: str, security_id: str, epoch: int) -> int:
    normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
    normalized_security_id = normalize_lookup_identifier(security_id)
    lock_scope = (
        f"position-history-replay:{normalized_portfolio_id}:{normalized_security_id}:{epoch}"
    )
    digest = hashlib.blake2b(lock_scope.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, byteorder="big", signed=True)


class SqlAlchemyPositionHistoryRepository:
    """Implement position-history persistence in the caller-owned SQL transaction."""

    def __init__(self, session: AsyncSession, *, clock: Callable[[], float] = monotonic) -> None:
        self._session = session
        self._clock = clock

    @async_timed(repository="PositionRepository", method="acquire_position_history_replay_lock")
    async def acquire_replay_lock(self, *, portfolio_id: str, security_id: str, epoch: int) -> None:
        """Serialize destructive replay for one normalized position key and epoch."""
        lock_key = _position_history_replay_lock_key(portfolio_id, security_id, epoch)
        started_at = self._clock()
        try:
            await self._session.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)").bindparams(lock_key=lock_key)
            )
        except BaseException:
            wait_seconds = max(0.0, self._clock() - started_at)
            observe_position_history_replay_lock_wait(
                outcome="failed",
                seconds=wait_seconds,
            )
            logger.warning(
                "Position history replay lock acquisition failed.",
                extra={
                    "portfolio_id": normalize_lookup_identifier(portfolio_id),
                    "security_id": normalize_lookup_identifier(security_id),
                    "epoch": epoch,
                    "lock_wait_seconds": wait_seconds,
                },
                exc_info=True,
            )
            raise
        wait_seconds = max(0.0, self._clock() - started_at)
        observe_position_history_replay_lock_wait(
            outcome="acquired",
            seconds=wait_seconds,
        )
        logger.debug(
            "Position history replay lock acquired.",
            extra={
                "portfolio_id": normalize_lookup_identifier(portfolio_id),
                "security_id": normalize_lookup_identifier(security_id),
                "epoch": epoch,
                "lock_wait_seconds": wait_seconds,
            },
        )

    @async_timed(repository="PositionRepository", method="load_materialization_progress")
    async def load_materialization_progress(
        self, *, portfolio_id: str, security_id: str, epoch: int
    ) -> PositionMaterializationProgress:
        """Load both epoch progress boundaries in one database round trip."""
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        normalized_security_id = normalize_lookup_identifier(security_id)
        latest_history_date = (
            select(func.max(PositionHistory.position_date))
            .where(
                func.trim(PositionHistory.portfolio_id) == normalized_portfolio_id,
                func.trim(PositionHistory.security_id) == normalized_security_id,
                PositionHistory.epoch == epoch,
            )
            .scalar_subquery()
        )
        latest_completed_snapshot_date = (
            select(func.max(DailyPositionSnapshot.date))
            .where(
                func.trim(DailyPositionSnapshot.portfolio_id) == normalized_portfolio_id,
                func.trim(DailyPositionSnapshot.security_id) == normalized_security_id,
                DailyPositionSnapshot.epoch == epoch,
            )
            .scalar_subquery()
        )
        statement = select(
            latest_history_date.label("latest_history_date"),
            latest_completed_snapshot_date.label("latest_completed_snapshot_date"),
        )
        result = await self._session.execute(statement)
        history_date, snapshot_date = result.one()
        return PositionMaterializationProgress(
            latest_history_date=cast(date | None, history_date),
            latest_completed_snapshot_date=cast(date | None, snapshot_date),
        )

    @async_timed(repository="PositionRepository", method="is_transaction_materialized")
    async def contains_transaction(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        transaction_id: str,
        epoch: int,
    ) -> bool:
        """Return whether the epoch already contains the transaction lineage."""
        statement = (
            select(PositionHistory.id)
            .where(
                func.trim(PositionHistory.portfolio_id)
                == normalize_lookup_identifier(portfolio_id),
                func.trim(PositionHistory.security_id) == normalize_lookup_identifier(security_id),
                func.trim(PositionHistory.transaction_id)
                == normalize_lookup_identifier(transaction_id),
                PositionHistory.epoch == epoch,
            )
            .limit(1)
        )
        return (await self._session.execute(statement)).scalar_one_or_none() is not None

    @async_timed(repository="PositionRepository", method="get_all_transactions_for_security")
    async def list_all_transactions(
        self, *, portfolio_id: str, security_id: str
    ) -> tuple[BookedTransaction, ...]:
        """Return every booked transaction for one position key."""
        statement = (
            select(Transaction)
            .where(
                func.trim(Transaction.portfolio_id) == normalize_lookup_identifier(portfolio_id),
                func.trim(Transaction.security_id) == normalize_lookup_identifier(security_id),
            )
            .order_by(Transaction.transaction_date.asc(), Transaction.transaction_id.asc())
        )
        result = await self._session.execute(statement)
        return tuple(_to_booked_transaction(row) for row in result.scalars().all())

    @async_timed(repository="PositionRepository", method="reset_and_load_position_replay_window")
    async def reset_and_load_replay_window(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        position_date: date,
        epoch: int,
    ) -> PositionReplayWindow:
        """Delete the stale suffix and load its replay inputs in one statement.

        PostgreSQL data-modifying CTEs share the statement snapshot. The anchor
        predicate reads only rows before ``position_date``, so it is intentionally
        unaffected by the suffix deletion while the caller avoids a second round
        trip inside the position-key lock.
        """
        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        normalized_security_id = normalize_lookup_identifier(security_id)
        deleted_suffix = (
            delete(PositionHistory)
            .where(
                func.trim(PositionHistory.portfolio_id) == normalized_portfolio_id,
                func.trim(PositionHistory.security_id) == normalized_security_id,
                PositionHistory.position_date >= position_date,
                PositionHistory.epoch == epoch,
            )
            .returning(PositionHistory.id)
            .cte("deleted_position_history_suffix")
        )
        anchor_cte = (
            select(PositionHistory)
            .where(
                func.trim(PositionHistory.portfolio_id) == normalized_portfolio_id,
                func.trim(PositionHistory.security_id) == normalized_security_id,
                PositionHistory.position_date < position_date,
                PositionHistory.epoch == epoch,
            )
            .order_by(PositionHistory.position_date.desc(), PositionHistory.id.desc())
            .limit(1)
            .cte("position_replay_anchor")
        )
        anchor = aliased(PositionHistory, anchor_cte)
        statement = (
            select(Transaction, anchor)
            .add_cte(deleted_suffix)
            .select_from(Transaction)
            .outerjoin(anchor, true())
            .where(
                func.trim(Transaction.portfolio_id) == normalized_portfolio_id,
                func.trim(Transaction.security_id) == normalized_security_id,
                Transaction.transaction_date >= datetime.combine(position_date, time.min),
            )
            .order_by(Transaction.transaction_date.asc(), Transaction.transaction_id.asc())
        )
        rows = (await self._session.execute(statement)).all()
        anchor_row = rows[0][1] if rows else None
        logger.debug(
            "Reset stale position history and loaded replay window.",
            extra={
                "portfolio_id": normalized_portfolio_id,
                "security_id": normalized_security_id,
                "epoch": epoch,
                "position_date": position_date.isoformat(),
                "replay_transaction_count": len(rows),
            },
        )
        return PositionReplayWindow(
            anchor=(_to_position_history_record(anchor_row) if anchor_row is not None else None),
            transactions=tuple(_to_booked_transaction(row[0]) for row in rows),
        )

    @async_timed(repository="PositionRepository", method="delete_positions_from")
    async def delete_records_from(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        position_date: date,
        epoch: int,
    ) -> int:
        """Delete stale records in the caller-owned replay transaction."""
        statement = delete(PositionHistory).where(
            func.trim(PositionHistory.portfolio_id) == normalize_lookup_identifier(portfolio_id),
            func.trim(PositionHistory.security_id) == normalize_lookup_identifier(security_id),
            PositionHistory.position_date >= position_date,
            PositionHistory.epoch == epoch,
        )
        result = await self._session.execute(statement)
        deleted_count = result.rowcount or 0
        logger.debug(
            "Deleted stale position history records.",
            extra={
                "portfolio_id": normalize_lookup_identifier(portfolio_id),
                "security_id": normalize_lookup_identifier(security_id),
                "epoch": epoch,
                "position_date": position_date.isoformat(),
                "deleted_count": deleted_count,
            },
        )
        return int(deleted_count)

    @async_timed(repository="PositionRepository", method="save_positions")
    async def save_records(self, records: tuple[PositionHistoryRecord, ...]) -> None:
        """Stage domain history records for the caller-owned transaction commit."""
        if not records:
            return
        rows = [_to_position_history_row(record) for record in records]
        self._session.add_all(rows)
        logger.debug(
            "Staged position history records.",
            extra={"position_record_count": len(rows)},
        )


def _to_booked_transaction(row: Transaction) -> BookedTransaction:
    payload: dict[str, Any] = {}
    for field in fields(BookedTransaction):
        if hasattr(row, field.name):
            value = getattr(row, field.name)
        elif field.default is not MISSING:
            value = field.default
        else:
            raise ValueError(f"Transaction row is missing required field {field.name!r}")
        if field.name == "calculation_lineage":
            value = calculation_lineage_from_payload(value)
        elif field.name in _TUPLE_FIELDS and value is not None:
            value = tuple(value)
        payload[field.name] = value
    return BookedTransaction(**payload)


def _to_position_history_record(row: PositionHistory) -> PositionHistoryRecord:
    return PositionHistoryRecord(
        portfolio_id=str(row.portfolio_id),
        security_id=str(row.security_id),
        transaction_id=str(row.transaction_id),
        position_date=cast(date, row.position_date),
        quantity=Decimal(row.quantity),
        cost_basis=Decimal(row.cost_basis),
        cost_basis_local=Decimal(row.cost_basis_local or 0),
        epoch=int(row.epoch),
        calculation_lineage=calculation_lineage_from_payload(row.calculation_lineage),
    )


def _to_position_history_row(record: PositionHistoryRecord) -> PositionHistory:
    return PositionHistory(
        portfolio_id=record.portfolio_id,
        security_id=record.security_id,
        transaction_id=record.transaction_id,
        position_date=record.position_date,
        quantity=record.quantity,
        cost_basis=record.cost_basis,
        cost_basis_local=record.cost_basis_local,
        epoch=record.epoch,
        calculation_lineage=(
            record.calculation_lineage.lineage_payload()
            if record.calculation_lineage is not None
            else None
        ),
    )
