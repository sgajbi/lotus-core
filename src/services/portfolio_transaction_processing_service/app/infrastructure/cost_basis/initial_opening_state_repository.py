"""Atomic SQLAlchemy persistence for an initial opening cost state."""

from portfolio_common.utils import async_timed
from sqlalchemy import literal
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.cost_basis import CostBasisProcessingCheckpoint, CostBasisTransaction
from ...domain.transaction import BookedTransaction
from ..income.accrued_income_offset_repository import (
    accrued_income_offset_upsert_statement,
)
from .lot_state_repository import buy_lot_state_upsert_statement
from .processing_state_repository import cost_basis_processing_checkpoint_upsert_statement
from .transaction_repository import (
    persisted_booked_transaction_from_row,
    stage_transaction_cost_rows,
    transaction_economics_update_statement,
)


class SqlAlchemyInitialOpeningCostStateRepository:
    """Persist initial transaction economics and opening state in one statement."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @async_timed(
        repository="InitialOpeningCostStateRepository",
        method="persist_initial_opening_cost_state",
    )
    async def persist_initial_opening_cost_state(
        self,
        *,
        transaction: CostBasisTransaction,
        checkpoint: CostBasisProcessingCheckpoint,
    ) -> BookedTransaction | None:
        """Write transaction economics and all opening state through one round trip."""

        _validate_initial_opening_scope(transaction=transaction, checkpoint=checkpoint)
        opening_lot = (
            buy_lot_state_upsert_statement(transaction)
            .returning(literal(1))
            .cte("persist_initial_opening_lot")
        )
        income_offset = (
            accrued_income_offset_upsert_statement(transaction)
            .returning(literal(1))
            .cte("persist_initial_income_offset")
        )
        checkpoint_write = (
            cost_basis_processing_checkpoint_upsert_statement(checkpoint)
            .returning(literal(1))
            .cte("persist_initial_processing_checkpoint")
        )
        statement = transaction_economics_update_statement(
            transaction,
            additional_ctes=(opening_lot, income_offset, checkpoint_write),
        )
        db_transaction = (await self._session.execute(statement)).scalars().first()
        if db_transaction is None:
            return None
        stage_transaction_cost_rows(
            session=self._session,
            transaction_result=transaction,
            db_transaction=db_transaction,
        )
        return persisted_booked_transaction_from_row(db_transaction)


def _validate_initial_opening_scope(
    *,
    transaction: CostBasisTransaction,
    checkpoint: CostBasisProcessingCheckpoint,
) -> None:
    """Reject an aggregate assembled from different domain identities before SQL execution."""

    if (
        checkpoint.portfolio_id,
        checkpoint.security_id,
        checkpoint.latest_transaction_id,
    ) != (
        transaction.portfolio_id,
        transaction.security_id,
        transaction.transaction_id,
    ):
        raise ValueError(
            "Initial opening checkpoint scope must match the transaction portfolio, "
            "security, and transaction identity"
        )
