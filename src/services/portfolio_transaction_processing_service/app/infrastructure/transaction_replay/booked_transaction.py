"""Replay transport and typed reader over a single caller-owned SQL session."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Protocol

from portfolio_common.reprocessing_replay import (
    TRANSACTION_REPLAY_SOURCE_FIELD_NAMES,
    ReprocessingReplayError,
)
from portfolio_common.reprocessing_repository import load_transaction_replay_rows
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from ...application import (
    BookedTransactionReplayDependencyUnavailable,
    BookedTransactionReplayInvariantViolation,
)
from .fee_source_repository import load_qualified_transaction_fee_sources


class CanonicalTransactionReplayer(Protocol):
    """Describe the canonical publisher used by the replay adapter."""

    async def reprocess_transactions_by_ids(
        self,
        transaction_ids: list[str],
        *,
        correlation_id: str | None = None,
        repair_delivery_id: str | None = None,
    ) -> int: ...


@dataclass(frozen=True, slots=True)
class SqlAlchemyBookedTransactionReplayAdapter:
    """Replay one transaction using a fresh SQLAlchemy session."""

    session_factory: Callable[[], AsyncSession]
    replayer_factory: Callable[[AsyncSession], CanonicalTransactionReplayer]

    async def replay_booked_transaction(
        self,
        *,
        transaction_id: str,
        correlation_id: str | None,
        repair_delivery_id: str | None = None,
    ) -> bool:
        try:
            async with self.session_factory() as session:
                replayer = self.replayer_factory(session)
                if repair_delivery_id is None:
                    replayed_count = await replayer.reprocess_transactions_by_ids(
                        [transaction_id],
                        correlation_id=correlation_id,
                    )
                else:
                    replayed_count = await replayer.reprocess_transactions_by_ids(
                        [transaction_id],
                        correlation_id=correlation_id,
                        repair_delivery_id=repair_delivery_id,
                    )
        except (DBAPIError, ReprocessingReplayError) as exc:
            raise BookedTransactionReplayDependencyUnavailable(
                "Canonical booked transaction replay dependency unavailable"
            ) from exc
        if replayed_count not in {0, 1}:
            raise BookedTransactionReplayInvariantViolation(
                "Canonical booked transaction replay must publish zero or one record; "
                f"transaction_id={transaction_id}, replayed_count={replayed_count}"
            )
        return replayed_count == 1


@dataclass(frozen=True, slots=True)
class SqlAlchemyQualifiedTransactionReplayReader:
    """Own typed material qualification while shared SQL stays policy-neutral."""

    session: AsyncSession

    async def list_transactions_to_replay(self, transaction_ids: list[str]) -> list[Any]:
        rows = await load_transaction_replay_rows(self.session, transaction_ids, lock_sources=True)
        projections = await load_qualified_transaction_fee_sources(
            self.session, rows, lock_sources=True, allow_retained_receipt=True
        )
        return [
            SimpleNamespace(
                **{
                    key: value
                    for key, value in (dict(row) | projections[row["transaction_id"]]).items()
                    if key in TRANSACTION_REPLAY_SOURCE_FIELD_NAMES
                }
            )
            for row in rows
        ]
