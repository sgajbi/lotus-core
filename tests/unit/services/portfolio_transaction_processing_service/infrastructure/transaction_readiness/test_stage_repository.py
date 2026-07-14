"""Verify transaction-readiness stage persistence and epoch fencing."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.domain import (
    TransactionStageRecord,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_readiness import (  # noqa: E501
    SqlAlchemyTransactionStageRepository,
)


def _persisted_stage(*, portfolio_id: str = "PB-001") -> SimpleNamespace:
    return SimpleNamespace(
        id=12,
        transaction_id="TX-READY-001",
        portfolio_id=portfolio_id,
        security_id="SEC-001",
        business_date=date(2026, 4, 10),
        epoch=4,
        status="PENDING",
        cost_event_seen=True,
    )


def _stage_record() -> TransactionStageRecord:
    return TransactionStageRecord(
        stage_id=12,
        transaction_id="TX-READY-001",
        portfolio_id="PB-001",
        security_id="SEC-001",
        business_date=date(2026, 4, 10),
        epoch=4,
        status="PENDING",
        cost_event_seen=True,
    )


@pytest.mark.asyncio
async def test_acquire_stage_lock_uses_complete_transaction_stage_identity() -> None:
    session = AsyncMock(spec=AsyncSession)
    repository = SqlAlchemyTransactionStageRepository(session)

    await repository.acquire_stage_lock(
        stage_name="transaction_processing",
        portfolio_id="PB-001",
        transaction_id="TX-READY-001",
    )

    statement, parameters = session.execute.await_args.args
    assert str(statement) == ("SELECT pg_advisory_xact_lock(hashtextextended(:lock_identity, 0))")
    assert parameters == {
        "lock_identity": ("pipeline-stage:transaction_processing:PB-001:TX-READY-001")
    }


@pytest.mark.asyncio
async def test_latest_epoch_returns_current_transaction_stage_epoch() -> None:
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one_or_none.return_value = 7
    session.execute.return_value = result
    repository = SqlAlchemyTransactionStageRepository(session)

    epoch = await repository.latest_epoch(
        stage_name="transaction_processing",
        portfolio_id="PB-001",
        transaction_id="TX-READY-001",
    )

    assert epoch == 7
    statement = session.execute.await_args.args[0]
    compiled_query = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "max(pipeline_stage_state.epoch)" in compiled_query
    assert "pipeline_stage_state.stage_name = 'transaction_processing'" in compiled_query
    assert "pipeline_stage_state.portfolio_id = 'PB-001'" in compiled_query
    assert "pipeline_stage_state.transaction_id = 'TX-READY-001'" in compiled_query


@pytest.mark.asyncio
async def test_upsert_processed_stage_maps_persisted_state_to_domain_record() -> None:
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one.return_value = _persisted_stage()
    session.execute.return_value = result
    repository = SqlAlchemyTransactionStageRepository(session)

    stage = await repository.upsert_processed_stage(
        stage_name="transaction_processing",
        transaction_id="TX-READY-001",
        portfolio_id="PB-001",
        security_id="SEC-001",
        business_date=date(2026, 4, 10),
        epoch=4,
    )

    assert stage == _stage_record()
    statement = session.execute.await_args.args[0]
    assert statement.get_execution_options()["populate_existing"] is True
    compiled_query = str(statement.compile())
    assert "ON CONFLICT (stage_name, transaction_id, epoch) DO UPDATE" in compiled_query
    assert "RETURNING" in compiled_query


@pytest.mark.asyncio
async def test_upsert_processed_stage_rejects_cross_portfolio_key_collision() -> None:
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one.return_value = _persisted_stage(portfolio_id="PB-OTHER")
    session.execute.return_value = result
    repository = SqlAlchemyTransactionStageRepository(session)

    with pytest.raises(
        ValueError,
        match=(
            "Pipeline stage key collision detected for different portfolios: "
            "transaction_processing/TX-READY-001/4 "
            "existing=PB-OTHER incoming=PB-001"
        ),
    ):
        await repository.upsert_processed_stage(
            stage_name="transaction_processing",
            transaction_id="TX-READY-001",
            portfolio_id="PB-001",
            security_id="SEC-001",
            business_date=date(2026, 4, 10),
            epoch=4,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(("rowcount", "expected"), [(1, True), (0, False)])
async def test_claim_completion_reports_atomic_transition_result(
    rowcount: int,
    expected: bool,
) -> None:
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.rowcount = rowcount
    session.execute.return_value = result
    repository = SqlAlchemyTransactionStageRepository(session)

    claimed = await repository.claim_completion(_stage_record())

    assert claimed is expected
    statement = session.execute.await_args.args[0]
    compiled_query = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "pipeline_stage_state.id = 12" in compiled_query
    assert "pipeline_stage_state.status = 'PENDING'" in compiled_query
    assert "pipeline_stage_state.cost_event_seen IS true" in compiled_query
    assert "status='COMPLETED'" in compiled_query.replace(" ", "")
