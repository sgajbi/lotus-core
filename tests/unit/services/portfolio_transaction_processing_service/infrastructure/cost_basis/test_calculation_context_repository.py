"""Verify the post-lock cost-basis calculation context read model."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    calculation_context_repository as repository_module,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis.calculation_context_repository import (  # noqa: E501
    SqlAlchemyCostBasisCalculationContextRepository,
)

pytestmark = pytest.mark.asyncio


def _session_with_rows(*rows: tuple[object | None, object | None]) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = list(rows)
    session.execute.return_value = result
    return session


async def test_context_returns_checkpoint_without_rehydrating_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint_row = SimpleNamespace(portfolio_id="PB-001", security_id="SEC-001")
    mapped_checkpoint = MagicMock(name="mapped_checkpoint")
    map_checkpoint = MagicMock(return_value=mapped_checkpoint)
    map_transaction = MagicMock()
    monkeypatch.setattr(
        repository_module,
        "cost_basis_processing_checkpoint_from_row",
        map_checkpoint,
    )
    monkeypatch.setattr(
        repository_module,
        "persisted_to_booked_transaction",
        map_transaction,
    )
    session = _session_with_rows((checkpoint_row, None))

    context = await SqlAlchemyCostBasisCalculationContextRepository(
        session
    ).load_cost_basis_calculation_context(
        portfolio_id=" pb-001 ",
        security_id=" sec-001 ",
        exclude_transaction_id=" tx-new ",
        include_initial_history=True,
    )

    assert context.checkpoint is mapped_checkpoint
    assert context.transaction_history is None
    map_checkpoint.assert_called_once_with(checkpoint_row)
    map_transaction.assert_not_called()
    session.execute.assert_awaited_once()


async def test_context_returns_ordered_initial_history_when_checkpoint_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_row = MagicMock(name="first_transaction_row")
    second_row = MagicMock(name="second_transaction_row")
    first = MagicMock(name="first_booked_transaction")
    second = MagicMock(name="second_booked_transaction")
    map_transaction = MagicMock(side_effect=(first, second))
    map_checkpoint = MagicMock()
    monkeypatch.setattr(
        repository_module,
        "cost_basis_processing_checkpoint_from_row",
        map_checkpoint,
    )
    monkeypatch.setattr(
        repository_module,
        "persisted_to_booked_transaction",
        map_transaction,
    )
    session = _session_with_rows((None, first_row), (None, second_row))

    context = await SqlAlchemyCostBasisCalculationContextRepository(
        session
    ).load_cost_basis_calculation_context(
        portfolio_id="PB-001",
        security_id="SEC-001",
        exclude_transaction_id="TX-NEW",
        include_initial_history=True,
    )

    assert context.checkpoint is None
    assert context.transaction_history == (first, second)
    map_checkpoint.assert_not_called()
    assert map_transaction.call_args_list == [
        call(first_row),
        call(second_row),
    ]
    session.execute.assert_awaited_once()
    statement = session.execute.await_args.args[0]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "trim(transactions_1.portfolio_id) = 'PB-001'" in compiled
    assert "trim(transactions_1.security_id) = 'SEC-001'" in compiled
    assert "trim(transactions_1.transaction_id) != 'TX-NEW'" in compiled


async def test_context_distinguishes_skipped_history_from_empty_history() -> None:
    session = _session_with_rows((None, None))

    context = await SqlAlchemyCostBasisCalculationContextRepository(
        session
    ).load_cost_basis_calculation_context(
        portfolio_id="PB-001",
        security_id="SEC-001",
        exclude_transaction_id="TX-NEW",
        include_initial_history=False,
    )

    assert context.checkpoint is None
    assert context.transaction_history is None
    session.execute.assert_awaited_once()


async def test_context_fails_closed_if_database_does_not_return_seed_row() -> None:
    session = _session_with_rows()

    with pytest.raises(RuntimeError, match="returned no seed row"):
        await SqlAlchemyCostBasisCalculationContextRepository(
            session
        ).load_cost_basis_calculation_context(
            portfolio_id="PB-001",
            security_id="SEC-001",
            exclude_transaction_id="TX-NEW",
            include_initial_history=True,
        )

    session.execute.assert_awaited_once()
