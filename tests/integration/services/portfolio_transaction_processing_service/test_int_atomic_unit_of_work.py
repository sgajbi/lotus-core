from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import OutboxEvent, ProcessedEvent
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.portfolio_transaction_processing_service.app.application import (
    ProcessTransactionCommand,
    ProcessTransactionUseCase,
    TransactionEventMetadata,
    TransactionProcessingStatus,
)
from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    TRANSACTION_PROCESSING_SERVICE_NAME,
    SqlAlchemyTransactionProcessingUnitOfWork,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    CashflowProcessingResult,
    CostProcessingResult,
    PositionProcessingResult,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration_db,
    pytest.mark.db_direct,
    pytest.mark.regression,
    pytest.mark.resilience,
]


def _command(suffix: str) -> ProcessTransactionCommand:
    return ProcessTransactionCommand(
        transaction=BookedTransaction(
            transaction_id=f"TX-UOW-{suffix}",
            portfolio_id=f"PB-UOW-{suffix}",
            instrument_id="INST-UOW-001",
            security_id="SEC-UOW-001",
            transaction_date=datetime(2026, 4, 10, 9, 30, tzinfo=timezone.utc),
            transaction_type="BUY",
            quantity=Decimal("10"),
            price=Decimal("25.50"),
            gross_transaction_amount=Decimal("255.00"),
            trade_currency="SGD",
            currency="SGD",
        ),
        metadata=TransactionEventMetadata(
            event_id=f"transactions.persisted-0-{suffix}",
            correlation_id=f"corr-{suffix}",
        ),
    )


class _StagingModule:
    def __init__(self, session: AsyncSession, module_name: str, fail_at: str | None) -> None:
        self._session = session
        self._module_name = module_name
        self._fail_at = fail_at

    async def _stage(self, transaction: BookedTransaction) -> None:
        self._session.add(
            OutboxEvent(
                aggregate_type="AtomicTransactionProcessingProof",
                aggregate_id=transaction.transaction_id,
                event_type=f"{self._module_name}.staged",
                payload={"module": self._module_name},
                topic="transaction-processing.atomic-proof",
                correlation_id=f"corr-{transaction.transaction_id}",
            )
        )
        await self._session.flush()
        if self._fail_at == self._module_name:
            raise RuntimeError(f"{self._module_name} failed")


class _CostModule(_StagingModule):
    async def process(self, transaction: BookedTransaction, **_kwargs) -> CostProcessingResult:
        await self._stage(transaction)
        return CostProcessingResult(processed_transactions=(transaction,))


class _CashflowModule(_StagingModule):
    async def process(self, transaction: BookedTransaction, **_kwargs) -> CashflowProcessingResult:
        await self._stage(transaction)
        return CashflowProcessingResult(cashflow_record_count=1)


class _PositionModule(_StagingModule):
    async def process(self, transaction: BookedTransaction, **_kwargs) -> PositionProcessingResult:
        await self._stage(transaction)
        return PositionProcessingResult(position_record_count=1)


class _AtomicProofUnitOfWork(SqlAlchemyTransactionProcessingUnitOfWork):
    def __init__(self, *, fail_at: str | None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._fail_at = fail_at

    async def __aenter__(self):
        await super().__aenter__()
        assert self._session is not None
        self._cost = _CostModule(self._session, "cost", self._fail_at)
        self._cashflow = _CashflowModule(self._session, "cashflow", self._fail_at)
        self._position = _PositionModule(self._session, "position", self._fail_at)
        return self


def _unit_of_work_factory(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    fail_at: str | None,
):
    return lambda: _AtomicProofUnitOfWork(
        session_factory=session_factory,
        cost_workflow=object(),
        cashflow_workflow=object(),
        fail_at=fail_at,
    )


async def _persisted_counts(
    session_factory: async_sessionmaker[AsyncSession],
    command: ProcessTransactionCommand,
) -> tuple[int, int]:
    async with session_factory() as session:
        outbox_count = await session.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.aggregate_id == command.transaction.transaction_id)
        )
        idempotency_count = await session.scalar(
            select(func.count())
            .select_from(ProcessedEvent)
            .where(
                ProcessedEvent.event_id == command.metadata.event_id,
                ProcessedEvent.service_name == TRANSACTION_PROCESSING_SERVICE_NAME,
            )
        )
    return int(outbox_count or 0), int(idempotency_count or 0)


async def test_combined_use_case_commits_every_module_and_idempotency_atomically(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    command = _command("SUCCESS")
    use_case = ProcessTransactionUseCase(_unit_of_work_factory(session_factory, fail_at=None))

    result = await use_case.execute(command)
    duplicate_result = await use_case.execute(command)

    assert result.status is TransactionProcessingStatus.PROCESSED
    assert duplicate_result.status is TransactionProcessingStatus.DUPLICATE
    assert await _persisted_counts(session_factory, command) == (3, 1)


@pytest.mark.parametrize("fail_at", ["cost", "cashflow", "position"])
async def test_combined_use_case_rolls_back_every_module_and_idempotency_on_failure(
    clean_db,
    async_db_session: AsyncSession,
    fail_at: str,
) -> None:
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    command = _command(fail_at.upper())
    use_case = ProcessTransactionUseCase(_unit_of_work_factory(session_factory, fail_at=fail_at))

    with pytest.raises(RuntimeError, match=f"{fail_at} failed"):
        await use_case.execute(command)

    assert await _persisted_counts(session_factory, command) == (0, 0)
