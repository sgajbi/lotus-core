"""Verify bounded SQL ownership for lot-to-position parity evidence."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis.lot_position_reconciliation import (  # noqa: E501
    SqlAlchemyLotPositionParityAdapter,
)


@pytest.mark.asyncio
async def test_audit_uses_one_statement_and_scopes_candidates_to_governed_lots() -> None:
    session = MagicMock()
    result = MagicMock()
    result.all.return_value = []
    session.execute = AsyncMock(return_value=result)
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=None)
    session_factory = MagicMock(return_value=session_context)

    assessments = await SqlAlchemyLotPositionParityAdapter(
        session_factory=session_factory
    ).assess_page(portfolio_id=None, after=None, limit=1000)

    assert assessments == ()
    session.execute.assert_awaited_once()
    statement = session.execute.await_args.args[0]
    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "EXISTS (SELECT position_lot_state.id" in compiled
    assert "trim(position_lot_state.portfolio_id) = trim(position_state.portfolio_id)" in compiled
    assert "trim(position_lot_state.security_id) = trim(position_state.security_id)" in compiled
    assert "trim(position_history.security_id) = trim(lot_position_parity_keys.security_id)" in (
        compiled
    )
    assert "LIMIT 1000" in compiled
