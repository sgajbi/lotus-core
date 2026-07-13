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
from portfolio_common.identifiers import normalize_lookup_identifier
from portfolio_common.monitoring import observe_position_history_replay_lock_wait
from portfolio_common.utils import async_timed
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.booked_transaction import BookedTransaction
from ..domain.position.history import PositionHistoryRecord

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
        logger.info(
            "Position history replay lock acquired.",
            extra={
                "portfolio_id": normalize_lookup_identifier(portfolio_id),
                "security_id": normalize_lookup_identifier(security_id),
                "epoch": epoch,
                "lock_wait_seconds": wait_seconds,
            },
        )

    @async_timed(repository="PositionRepository", method="get_latest_completed_snapshot_date")
    async def latest_completed_snapshot_date(
        self, *, portfolio_id: str, security_id: str, epoch: int
    ) -> date | None:
        """Return the latest completed daily snapshot date for the position epoch."""
        statement = select(func.max(DailyPositionSnapshot.date)).where(
            func.trim(DailyPositionSnapshot.portfolio_id)
            == normalize_lookup_identifier(portfolio_id),
            func.trim(DailyPositionSnapshot.security_id)
            == normalize_lookup_identifier(security_id),
            DailyPositionSnapshot.epoch == epoch,
        )
        result = await self._session.execute(statement)
        return cast(date | None, result.scalar_one_or_none())

    @async_timed(repository="PositionRepository", method="get_latest_position_history_date")
    async def latest_history_date(
        self, *, portfolio_id: str, security_id: str, epoch: int
    ) -> date | None:
        """Return the latest materialized position-history date for the epoch."""
        statement = select(func.max(PositionHistory.position_date)).where(
            func.trim(PositionHistory.portfolio_id) == normalize_lookup_identifier(portfolio_id),
            func.trim(PositionHistory.security_id) == normalize_lookup_identifier(security_id),
            PositionHistory.epoch == epoch,
        )
        result = await self._session.execute(statement)
        return cast(date | None, result.scalar_one_or_none())

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

    @async_timed(repository="PositionRepository", method="get_last_position_before")
    async def last_record_before(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        position_date: date,
        epoch: int,
    ) -> PositionHistoryRecord | None:
        """Return the latest position record before the replay window."""
        statement = (
            select(PositionHistory)
            .where(
                func.trim(PositionHistory.portfolio_id)
                == normalize_lookup_identifier(portfolio_id),
                func.trim(PositionHistory.security_id) == normalize_lookup_identifier(security_id),
                PositionHistory.position_date < position_date,
                PositionHistory.epoch == epoch,
            )
            .order_by(PositionHistory.position_date.desc(), PositionHistory.id.desc())
        )
        result = await self._session.execute(statement)
        row = result.scalars().first()
        return _to_position_history_record(row) if row is not None else None

    @async_timed(repository="PositionRepository", method="get_transactions_on_or_after")
    async def list_transactions_from(
        self, *, portfolio_id: str, security_id: str, transaction_date: date
    ) -> tuple[BookedTransaction, ...]:
        """Return booked transactions in the affected replay window."""
        statement = (
            select(Transaction)
            .where(
                func.trim(Transaction.portfolio_id) == normalize_lookup_identifier(portfolio_id),
                func.trim(Transaction.security_id) == normalize_lookup_identifier(security_id),
                Transaction.transaction_date >= datetime.combine(transaction_date, time.min),
            )
            .order_by(Transaction.transaction_date.asc(), Transaction.transaction_id.asc())
        )
        result = await self._session.execute(statement)
        return tuple(_to_booked_transaction(row) for row in result.scalars().all())

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
        logger.info(
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
        """Map domain history records to ORM rows and flush them without committing."""
        if not records:
            return
        rows = [_to_position_history_row(record) for record in records]
        self._session.add_all(rows)
        await self._session.flush()
        logger.info(
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
        if field.name in _TUPLE_FIELDS and value is not None:
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
    )
