from __future__ import annotations

from dataclasses import replace
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
    TransactionProcessingIntent,
    TransactionProcessingRejected,
    TransactionProcessingStatus,
)
from src.services.portfolio_transaction_processing_service.app.domain import (
    BookedTransaction,
    build_transaction_correction_identity,
    build_transaction_semantic_identity,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    PROMETHEUS_TRANSACTION_PROCESSING_OBSERVER,
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
    use_case = ProcessTransactionUseCase(
        _unit_of_work_factory(session_factory, fail_at=None),
        observer=PROMETHEUS_TRANSACTION_PROCESSING_OBSERVER,
    )

    result = await use_case.execute(command)
    duplicate_result = await use_case.execute(command)

    assert result.status is TransactionProcessingStatus.PROCESSED
    assert duplicate_result.status is TransactionProcessingStatus.DUPLICATE
    assert await _persisted_counts(session_factory, command) == (3, 1)


@pytest.mark.parametrize("republished", [False, True])
async def test_historical_fee_dominated_delivery_remains_an_idempotent_duplicate(
    clean_db,
    async_db_session: AsyncSession,
    republished: bool,
) -> None:
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    command = _command("HISTORICAL-FEE-DOMINATED")
    command = replace(
        command,
        transaction=replace(
            command.transaction,
            transaction_type="SELL",
            gross_transaction_amount=Decimal("100"),
            trade_fee=Decimal("100"),
        ),
    )
    identity = build_transaction_semantic_identity(command.transaction)
    historical_event_id = (
        "transactions.persisted-0-historical" if republished else command.metadata.event_id
    )
    async with session_factory() as session:
        session.add(
            ProcessedEvent(
                event_id=historical_event_id,
                portfolio_id=command.transaction.portfolio_id,
                service_name=TRANSACTION_PROCESSING_SERVICE_NAME,
                correlation_id="corr-historical",
                semantic_key=identity.semantic_key,
                payload_fingerprint=identity.payload_fingerprint,
            )
        )
        await session.commit()

    result = await ProcessTransactionUseCase(
        _unit_of_work_factory(session_factory, fail_at=None),
        observer=PROMETHEUS_TRANSACTION_PROCESSING_OBSERVER,
    ).execute(command)

    assert result.status is TransactionProcessingStatus.DUPLICATE
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
                ProcessedEvent.service_name == TRANSACTION_PROCESSING_SERVICE_NAME,
                ProcessedEvent.semantic_key == identity.semantic_key,
            )
        )
    assert int(outbox_count or 0) == 0
    assert int(idempotency_count or 0) == 1


async def test_semantic_fence_suppresses_republication_and_rejects_changed_payload(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    command = _command("SEMANTIC")
    republished = replace(
        command,
        metadata=replace(command.metadata, event_id="transactions.replayed-4-900"),
    )
    conflicting = replace(
        republished,
        transaction=replace(
            republished.transaction,
            gross_transaction_amount=Decimal("256.00"),
        ),
        metadata=replace(republished.metadata, event_id="transactions.corrected-1-901"),
    )
    use_case = ProcessTransactionUseCase(
        _unit_of_work_factory(session_factory, fail_at=None),
        observer=PROMETHEUS_TRANSACTION_PROCESSING_OBSERVER,
    )

    first_result = await use_case.execute(command)
    duplicate_result = await use_case.execute(republished)
    with pytest.raises(TransactionProcessingRejected) as exc_info:
        await use_case.execute(conflicting)

    assert first_result.status is TransactionProcessingStatus.PROCESSED
    assert duplicate_result.status is TransactionProcessingStatus.DUPLICATE
    assert exc_info.value.reason_code == "transaction_semantic_conflict"
    assert await _persisted_counts(session_factory, command) == (3, 1)
    async with session_factory() as session:
        semantic_fence_count = await session.scalar(
            select(func.count())
            .select_from(ProcessedEvent)
            .where(
                ProcessedEvent.service_name == TRANSACTION_PROCESSING_SERVICE_NAME,
                ProcessedEvent.semantic_key
                == "transaction-processing:v1:PB-UOW-SEMANTIC:TX-UOW-SEMANTIC:0",
            )
        )
    assert semantic_fence_count == 1


@pytest.mark.parametrize(
    ("transaction_type", "gross_amount", "fee_amount", "withholding_tax", "reason_code"),
    [
        ("SELL", "100", "100", None, "SELL_010_NON_POSITIVE_NET_SETTLEMENT"),
        ("DIVIDEND", "100", "100.01", None, "DIVIDEND_013_NON_POSITIVE_NET_SETTLEMENT"),
        ("INTEREST", "10", "8", "2", "INTEREST_017_NON_POSITIVE_NET_SETTLEMENT"),
    ],
)
async def test_fee_dominated_settlement_replay_leaves_no_state_before_corrected_delivery(
    clean_db,
    async_db_session: AsyncSession,
    transaction_type: str,
    gross_amount: str,
    fee_amount: str,
    withholding_tax: str | None,
    reason_code: str,
) -> None:
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    base_command = _command(f"FEE-DOMINATED-{transaction_type}")
    rejected_command = replace(
        base_command,
        transaction=replace(
            base_command.transaction,
            transaction_type=transaction_type,
            gross_transaction_amount=Decimal(gross_amount),
            trade_fee=Decimal(fee_amount),
            withholding_tax_amount=(
                Decimal(withholding_tax) if withholding_tax is not None else None
            ),
            interest_direction=("INCOME" if transaction_type == "INTEREST" else None),
        ),
    )
    use_case = ProcessTransactionUseCase(
        _unit_of_work_factory(session_factory, fail_at=None),
        observer=PROMETHEUS_TRANSACTION_PROCESSING_OBSERVER,
    )

    for _delivery in range(2):
        with pytest.raises(TransactionProcessingRejected) as raised:
            await use_case.execute(rejected_command)
        assert raised.value.reason_code == reason_code

    assert await _persisted_counts(session_factory, rejected_command) == (0, 0)

    corrected_command = replace(
        rejected_command,
        transaction=replace(rejected_command.transaction, trade_fee=Decimal("1")),
    )
    corrected_result = await use_case.execute(corrected_command)
    duplicate_result = await use_case.execute(corrected_command)

    assert corrected_result.status is TransactionProcessingStatus.PROCESSED
    assert duplicate_result.status is TransactionProcessingStatus.DUPLICATE
    assert await _persisted_counts(session_factory, corrected_command) == (3, 1)


async def test_explicit_repair_claims_immutable_payload_specific_correction_identity(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    original = _command("CORRECTION")
    corrected = replace(
        original,
        transaction=replace(
            original.transaction,
            quantity=Decimal("12"),
            gross_transaction_amount=Decimal("306.00"),
        ),
        metadata=replace(
            original.metadata,
            event_id="transactions.corrected-1-902",
            processing_intent=TransactionProcessingIntent.REPAIR,
        ),
    )
    use_case = ProcessTransactionUseCase(
        _unit_of_work_factory(session_factory, fail_at=None),
        observer=PROMETHEUS_TRANSACTION_PROCESSING_OBSERVER,
    )

    original_result = await use_case.execute(original)
    corrected_result = await use_case.execute(corrected)

    assert original_result.status is TransactionProcessingStatus.PROCESSED
    assert corrected_result.status is TransactionProcessingStatus.PROCESSED
    original_identity = build_transaction_semantic_identity(original.transaction)
    correction_identity = build_transaction_correction_identity(corrected.transaction)
    async with session_factory() as session:
        semantic_rows = (
            (
                await session.execute(
                    select(ProcessedEvent.semantic_key, ProcessedEvent.payload_fingerprint)
                    .where(
                        ProcessedEvent.service_name == TRANSACTION_PROCESSING_SERVICE_NAME,
                        ProcessedEvent.semantic_key.isnot(None),
                    )
                    .order_by(ProcessedEvent.id)
                )
            )
            .tuples()
            .all()
        )

    assert semantic_rows == [
        (original_identity.semantic_key, original_identity.payload_fingerprint),
        (correction_identity.semantic_key, correction_identity.payload_fingerprint),
    ]


@pytest.mark.parametrize("fail_at", ["cost", "cashflow", "position"])
async def test_combined_use_case_rolls_back_every_module_and_idempotency_on_failure(
    clean_db,
    async_db_session: AsyncSession,
    fail_at: str,
) -> None:
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    command = _command(fail_at.upper())
    use_case = ProcessTransactionUseCase(
        _unit_of_work_factory(session_factory, fail_at=fail_at),
        observer=PROMETHEUS_TRANSACTION_PROCESSING_OBSERVER,
    )

    with pytest.raises(RuntimeError, match=f"{fail_at} failed"):
        await use_case.execute(command)

    assert await _persisted_counts(session_factory, command) == (0, 0)
