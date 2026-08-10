"""Load the post-lock cost-basis frontier in one database round trip."""

from __future__ import annotations

from portfolio_common.database_models import CostBasisProcessingState
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.identifiers import normalize_lookup_identifier
from portfolio_common.utils import async_timed
from sqlalchemy import and_, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ...ports import CostBasisCalculationContext
from ..transaction_mapping.booked_transaction import persisted_to_booked_transaction
from .processing_state_repository import cost_basis_processing_checkpoint_from_row


class SqlAlchemyCostBasisCalculationContextRepository:
    """Read checkpoint ownership and initial history from one statement snapshot."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @async_timed(
        repository="CostBasisCalculationContextRepository",
        method="load_cost_basis_calculation_context",
    )
    async def load_cost_basis_calculation_context(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        exclude_transaction_id: str,
        include_initial_history: bool,
    ) -> CostBasisCalculationContext:
        """Load history only when no checkpoint exists and the caller needs it."""

        normalized_portfolio_id = normalize_lookup_identifier(portfolio_id)
        normalized_security_id = normalize_lookup_identifier(security_id)
        normalized_excluded_id = normalize_lookup_identifier(exclude_transaction_id)
        seed = select(literal(1).label("seed")).cte("cost_basis_context_seed")
        checkpoint = aliased(CostBasisProcessingState)
        transaction = aliased(DBTransaction)
        statement = (
            select(checkpoint, transaction)
            .select_from(seed)
            .outerjoin(
                checkpoint,
                and_(
                    checkpoint.portfolio_id == normalized_portfolio_id,
                    checkpoint.security_id == normalized_security_id,
                ),
            )
            .outerjoin(
                transaction,
                and_(
                    checkpoint.portfolio_id.is_(None),
                    literal(include_initial_history),
                    func.trim(transaction.portfolio_id) == normalized_portfolio_id,
                    func.trim(transaction.security_id) == normalized_security_id,
                    func.trim(transaction.transaction_id) != normalized_excluded_id,
                ),
            )
            .order_by(transaction.transaction_date.asc(), transaction.transaction_id.asc())
        )
        rows = (await self._session.execute(statement)).all()
        if not rows:
            raise RuntimeError("Cost-basis calculation context query returned no seed row")
        checkpoint_row = rows[0][0]
        if checkpoint_row is not None:
            return CostBasisCalculationContext(
                checkpoint=cost_basis_processing_checkpoint_from_row(checkpoint_row),
                transaction_history=None,
            )
        history = (
            tuple(
                persisted_to_booked_transaction(transaction_row)
                for _, transaction_row in rows
                if transaction_row is not None
            )
            if include_initial_history
            else None
        )
        return CostBasisCalculationContext(
            checkpoint=None,
            transaction_history=history,
        )
