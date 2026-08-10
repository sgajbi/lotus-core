"""Atomic SQLAlchemy persistence for an initial opening cost state."""

from portfolio_common.utils import async_timed
from sqlalchemy import literal
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.cost_basis import CostBasisProcessingCheckpoint, CostBasisTransaction
from ..income.accrued_income_offset_repository import (
    accrued_income_offset_upsert_statement,
)
from .lot_state_repository import buy_lot_state_upsert_statement
from .processing_state_repository import cost_basis_processing_checkpoint_upsert_statement


class SqlAlchemyInitialOpeningCostStateRepository:
    """Persist the initial lot, income offset, and checkpoint in one statement."""

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
    ) -> None:
        """Write all initial opening state atomically without extra database round trips."""

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
        checkpoint_statement = cost_basis_processing_checkpoint_upsert_statement(checkpoint)
        await self._session.execute(checkpoint_statement.add_cte(opening_lot, income_offset))
