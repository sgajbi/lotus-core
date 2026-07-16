"""SQLAlchemy adapter for authoritative transaction reprocessing identities."""

from __future__ import annotations

from collections.abc import Sequence

from portfolio_common.database_models import Transaction
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.transaction_reprocessing import TransactionReprocessingTarget
from ..ports.transaction_reprocessing import TransactionReprocessingTargetReadError


class SqlAlchemyTransactionReprocessingTargetReader:
    """Read transaction-to-portfolio identity from the canonical transaction ledger."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def read_targets(
        self,
        transaction_ids: Sequence[str],
    ) -> tuple[TransactionReprocessingTarget, ...]:
        try:
            result = await self._db.execute(
                select(Transaction.transaction_id, Transaction.portfolio_id).where(
                    Transaction.transaction_id.in_(tuple(transaction_ids))
                )
            )
        except SQLAlchemyError as exc:
            raise TransactionReprocessingTargetReadError(
                "Transaction reprocessing source lookup is unavailable."
            ) from exc
        return tuple(
            TransactionReprocessingTarget(
                transaction_id=str(row.transaction_id),
                portfolio_id=str(row.portfolio_id),
            )
            for row in result.all()
        )
