"""Verify transaction-readiness stage persistence and epoch fencing."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.domain import (
    TransactionStageRecord,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_readiness import (  # noqa: E501
    SqlAlchemyTransactionStageRepository,
)


def _stage_record() -> TransactionStageRecord:
    return TransactionStageRecord(
        stage_id=12,
        transaction_id="TX-READY-001",
        portfolio_id="PB-001",
        security_id="SEC-001",
        business_date=date(2026, 4, 10),
        epoch=4,
        status="COMPLETED",
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
async def test_claim_processed_stage_maps_new_completion_and_uses_one_statement() -> None:
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.mappings.return_value.one_or_none.return_value = {
        "id": 12,
        "transaction_id": "TX-READY-001",
        "portfolio_id": "PB-001",
        "security_id": "SEC-001",
        "business_date": date(2026, 4, 10),
        "epoch": 4,
        "status": "COMPLETED",
        "cost_event_seen": True,
        "newly_claimed": True,
    }
    session.execute.return_value = result
    repository = SqlAlchemyTransactionStageRepository(session)

    stage = await repository.claim_processed_stage(
        stage_name="transaction_processing",
        transaction_id="TX-READY-001",
        portfolio_id="PB-001",
        security_id="SEC-001",
        business_date=date(2026, 4, 10),
        epoch=4,
    )

    assert stage == _stage_record()
    session.execute.assert_awaited_once()
    statement, parameters = session.execute.await_args.args
    sql = str(statement)
    assert "WHERE NOT EXISTS" in sql
    assert "epoch > CAST(:epoch AS integer)" in sql
    assert "ON CONFLICT (stage_name, transaction_id, epoch) DO UPDATE" in sql
    assert "status = 'COMPLETED'" in sql
    assert "RETURNING" in sql
    assert parameters == {
        "stage_name": "transaction_processing",
        "transaction_id": "TX-READY-001",
        "portfolio_id": "PB-001",
        "security_id": "SEC-001",
        "business_date": date(2026, 4, 10),
        "epoch": 4,
    }


@pytest.mark.asyncio
async def test_claim_processed_stage_returns_none_for_same_owner_duplicate() -> None:
    session = AsyncMock(spec=AsyncSession)
    claim_result = MagicMock()
    claim_result.mappings.return_value.one_or_none.return_value = {
        "id": 12,
        "transaction_id": "TX-READY-001",
        "portfolio_id": "PB-001",
        "security_id": "SEC-001",
        "business_date": date(2026, 4, 10),
        "epoch": 4,
        "status": "COMPLETED",
        "cost_event_seen": True,
        "newly_claimed": False,
    }
    session.execute.return_value = claim_result
    repository = SqlAlchemyTransactionStageRepository(session)

    stage = await repository.claim_processed_stage(
        stage_name="transaction_processing",
        transaction_id="TX-READY-001",
        portfolio_id="PB-001",
        security_id="SEC-001",
        business_date=date(2026, 4, 10),
        epoch=4,
    )

    assert stage is None
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_claim_processed_stage_rejects_cross_portfolio_key_collision() -> None:
    session = AsyncMock(spec=AsyncSession)
    claim_result = MagicMock()
    claim_result.mappings.return_value.one_or_none.return_value = None
    owner_result = MagicMock()
    owner_result.scalar_one_or_none.return_value = "PB-OTHER"
    session.execute.side_effect = [claim_result, owner_result]
    repository = SqlAlchemyTransactionStageRepository(session)

    with pytest.raises(
        ValueError,
        match=(
            "Pipeline stage key collision detected for different portfolios: "
            "transaction_processing/TX-READY-001/4 "
            "existing=PB-OTHER incoming=PB-001"
        ),
    ):
        await repository.claim_processed_stage(
            stage_name="transaction_processing",
            transaction_id="TX-READY-001",
            portfolio_id="PB-001",
            security_id="SEC-001",
            business_date=date(2026, 4, 10),
            epoch=4,
        )
