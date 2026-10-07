"""Tests for the aggregate transaction-processing SQLAlchemy unit of work."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction

from src.services.portfolio_transaction_processing_service.app.application import (
    ProcessTransactionCashflowUseCase,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cashflow import (
    CashflowRuleCache,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_processing import (  # noqa: E501
    SqlAlchemyTransactionProcessingUnitOfWork,
)


def _unit_of_work():
    session = MagicMock(spec=AsyncSession)
    session.close = AsyncMock()
    transaction = AsyncMock(spec=AsyncSessionTransaction)
    session.begin.return_value = transaction
    unit_of_work = SqlAlchemyTransactionProcessingUnitOfWork(
        session_factory=lambda: session,
        cost_processor=MagicMock(),
        cashflow_rule_cache=CashflowRuleCache(),
    )
    return unit_of_work, session, transaction


@pytest.mark.asyncio
@pytest.mark.parametrize("capture_error", [False, True])
async def test_opt_in_backend_identity_uses_existing_setup_roundtrip_and_preserves_commit(
    monkeypatch, capture_error
):
    from src.services.portfolio_transaction_processing_service.app.ports import (
        processing_diagnostics as port,
    )

    unit, session, transaction = _unit_of_work()
    monkeypatch.setattr(port, "_callback_failures", 0)
    capture = MagicMock()
    if capture_error:
        capture.backend.side_effect = ValueError("capture refused")
    monkeypatch.setattr(port, "_factory", lambda *args: capture)
    birth = datetime.now(UTC)
    session.execute.return_value = MagicMock()
    session.execute.return_value.one.return_value = ("on", 41, birth, 7)
    with port.diagnostic_delivery("tenant_performance_load", "PERF_BALANCED_V1", "tx", None):
        async with unit:
            await unit.commit()
    assert session.execute.await_count == 2
    assert "pg_backend_pid()" in str(session.execute.await_args_list[0].args[0])
    capture.backend.assert_called_once_with(port.ProcessingBackendIdentity(41, birth, 7))
    transaction.commit.assert_awaited_once()
    transaction.rollback.assert_not_awaited()
    assert port.processing_diagnostic_failures() == int(capture_error)


@pytest.mark.asyncio
async def test_unit_of_work_builds_every_adapter_from_one_session_and_commits_once() -> None:
    unit_of_work, session, transaction = _unit_of_work()

    async with unit_of_work as entered:
        assert entered.idempotency is unit_of_work.idempotency
        assert entered.cost is unit_of_work.cost
        assert entered.cashflow is unit_of_work.cashflow
        assert isinstance(entered.cashflow, ProcessTransactionCashflowUseCase)
        assert entered.position is unit_of_work.position
        assert entered.readiness is unit_of_work.readiness
        await entered.commit()

    transaction.start.assert_awaited_once_with()
    transaction.commit.assert_awaited_once_with()
    assert session.execute.await_count == 2
    assert "cashflow_source_cut_deferred" in str(session.execute.await_args_list[0].args[0])
    assert str(session.execute.await_args_list[0].args[0]) == (
        "SELECT set_config('lotus.cashflow_source_cut_deferred', 'on', true)"
    )
    assert "flush_deferred_portfolio_cashflow_source_cuts" in str(
        session.execute.await_args_list[1].args[0]
    )
    transaction.rollback.assert_not_awaited()
    session.close.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize("raise_error", [False, True])
async def test_unit_of_work_rolls_back_uncommitted_duplicate_or_failure(
    raise_error: bool,
) -> None:
    unit_of_work, session, transaction = _unit_of_work()

    with pytest.raises(RuntimeError) if raise_error else nullcontext():
        async with unit_of_work:
            if raise_error:
                raise RuntimeError("module failed")

    transaction.commit.assert_not_awaited()
    transaction.start.assert_awaited_once_with()
    transaction.rollback.assert_awaited_once_with()
    session.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_unit_of_work_closes_session_when_transaction_start_fails() -> None:
    unit_of_work, session, transaction = _unit_of_work()
    transaction.start.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        async with unit_of_work:
            pytest.fail("unit of work should not enter")

    transaction.rollback.assert_not_awaited()
    session.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_unit_of_work_rolls_back_when_adapter_construction_fails() -> None:
    unit_of_work, session, transaction = _unit_of_work()
    unit_of_work._build_adapters = MagicMock(side_effect=RuntimeError("adapter unavailable"))

    with pytest.raises(RuntimeError, match="adapter unavailable"):
        async with unit_of_work:
            pytest.fail("unit of work should not enter")

    transaction.rollback.assert_awaited_once_with()
    session.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_unit_of_work_rejects_reuse_and_missing_adapters() -> None:
    unit_of_work, _session, _transaction = _unit_of_work()

    with pytest.raises(RuntimeError, match="idempotency adapter is not initialized"):
        _ = unit_of_work.idempotency

    async with unit_of_work:
        with pytest.raises(RuntimeError, match="cannot be reused"):
            await unit_of_work.__aenter__()


@pytest.mark.asyncio
async def test_unit_of_work_rejects_commit_without_an_active_transaction() -> None:
    unit_of_work, _session, _transaction = _unit_of_work()

    with pytest.raises(RuntimeError, match="has not been entered"):
        await unit_of_work.commit()


@pytest.mark.asyncio
async def test_unit_of_work_rejects_duplicate_commit_after_durable_flush() -> None:
    unit_of_work, _session, transaction = _unit_of_work()

    async with unit_of_work:
        await unit_of_work.commit()
        with pytest.raises(RuntimeError, match="already committed"):
            await unit_of_work.commit()

    transaction.commit.assert_awaited_once_with()
    transaction.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_unit_of_work_does_not_commit_when_the_deferred_cut_flush_fails() -> None:
    unit_of_work, session, transaction = _unit_of_work()
    session.execute.side_effect = (None, RuntimeError("source-cut flush failed"))

    with pytest.raises(RuntimeError, match="source-cut flush failed"):
        async with unit_of_work:
            await unit_of_work.commit()

    transaction.commit.assert_not_awaited()
    transaction.rollback.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_unit_of_work_rejects_commit_when_its_session_is_lost() -> None:
    unit_of_work, _session, transaction = _unit_of_work()
    unit_of_work._transaction = transaction
    unit_of_work._session = None

    with pytest.raises(RuntimeError, match="has no active session"):
        await unit_of_work.commit()


@pytest.mark.asyncio
async def test_unit_of_work_exit_tolerates_a_partially_initialised_boundary() -> None:
    unit_of_work, _session, _transaction = _unit_of_work()

    await unit_of_work.__aexit__(None, None, None)
