"""Verify the application use case that coordinates transaction processing."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from types import TracebackType

import pytest

from src.services.portfolio_transaction_processing_service.app.application import (
    ProcessTransactionCommand,
    ProcessTransactionUseCase,
    TransactionEventMetadata,
    TransactionProcessingIntent,
    TransactionProcessingRejected,
    TransactionProcessingStatus,
)
from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.domain.cashflow import (
    CashflowCalculationContext,
    CashflowClassification,
    CashflowRule,
    CashflowTiming,
    calculate_transaction_cashflow,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    build_generated_settlement_cash_leg,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    CashflowProcessingResult,
    CostProcessingResult,
    PositionProcessingResult,
    TransactionIdempotencyOutcome,
    TransactionProcessingOperation,
    TransactionProcessingOutcome,
)


class _RecordingObservation:
    def __init__(
        self,
        operation: TransactionProcessingOperation,
        records: list[tuple[TransactionProcessingOperation, TransactionProcessingOutcome]],
    ) -> None:
        self.operation = operation
        self.records = records
        self.outcome = TransactionProcessingOutcome.SUCCEEDED

    def set_outcome(self, outcome: TransactionProcessingOutcome) -> None:
        self.outcome = outcome

    def __enter__(self) -> _RecordingObservation:
        return self

    def __exit__(self, exc_type, _exc_value, _traceback) -> None:
        if exc_type is not None and self.outcome is TransactionProcessingOutcome.SUCCEEDED:
            self.outcome = TransactionProcessingOutcome.FAILED
        self.records.append((self.operation, self.outcome))


class _RecordingObserver:
    def __init__(self) -> None:
        self.records: list[tuple[TransactionProcessingOperation, TransactionProcessingOutcome]] = []

    def observe(self, operation: TransactionProcessingOperation) -> _RecordingObservation:
        return _RecordingObservation(operation, self.records)


def _transaction(transaction_id: str = "TX-001") -> BookedTransaction:
    return BookedTransaction(
        transaction_id=transaction_id,
        portfolio_id="PB-001",
        instrument_id="INST-001",
        security_id="SEC-001",
        transaction_date=datetime(2026, 4, 10, 9, 30, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("25.50"),
        gross_transaction_amount=Decimal("255.00"),
        trade_currency="SGD",
        currency="SGD",
    )


def _command() -> ProcessTransactionCommand:
    return ProcessTransactionCommand(
        transaction=_transaction(),
        metadata=TransactionEventMetadata(
            event_id="transactions.persisted-0-42",
            correlation_id="corr-001",
            traceparent="trace-001",
        ),
    )


class _Idempotency:
    def __init__(
        self,
        calls: list[str],
        *,
        outcome: TransactionIdempotencyOutcome = TransactionIdempotencyOutcome.CLAIMED,
    ) -> None:
        self.calls = calls
        self.outcomes = [outcome]
        self.claim_kwargs: dict = {}
        self.repair_claimed = True

    async def claim(self, **kwargs) -> TransactionIdempotencyOutcome:
        self.calls.append("idempotency")
        self.claim_kwargs = kwargs
        if len(self.outcomes) > 1:
            return self.outcomes.pop(0)
        return self.outcomes[0]

    async def claim_repair_delivery(self, **_kwargs) -> bool:
        self.calls.append("repair-idempotency")
        return self.repair_claimed


class _Cost:
    def __init__(
        self,
        calls: list[str],
        *,
        result: CostProcessingResult,
        error: Exception | None = None,
    ) -> None:
        self.calls = calls
        self.result = result
        self.error = error

    async def process(self, transaction: BookedTransaction, **_kwargs) -> CostProcessingResult:
        self.calls.append(f"cost:{transaction.transaction_id}")
        if self.error is not None:
            raise self.error
        return self.result


class _Cashflow:
    def __init__(self, calls: list[str], *, error: Exception | None = None) -> None:
        self.calls = calls
        self.error = error
        self.transactions: list[BookedTransaction] = []
        self.calculation_contexts: list[CashflowCalculationContext | None] = []
        self.locked_position_epochs: list[int | None] = []

    async def process(self, transaction: BookedTransaction, **kwargs) -> CashflowProcessingResult:
        self.calls.append(f"cashflow:{transaction.transaction_id}:{transaction.epoch or 0}")
        self.transactions.append(transaction)
        self.calculation_contexts.append(kwargs.get("calculation_context"))
        self.locked_position_epochs.append(kwargs.get("locked_position_epoch"))
        if self.error is not None:
            raise self.error
        return CashflowProcessingResult(cashflow_record_count=1)


class _Position:
    def __init__(
        self,
        calls: list[str],
        *,
        error_on: str | None = None,
        cashflow_rebuild_transactions_by_id: dict[str, tuple[BookedTransaction, ...]] | None = None,
        locked_state_epoch: int | None = None,
    ) -> None:
        self.calls = calls
        self.error_on = error_on
        self.cashflow_rebuild_transactions_by_id = cashflow_rebuild_transactions_by_id or {}
        self.locked_state_epoch = locked_state_epoch
        self.rebuild_existing_calls: list[bool] = []

    async def process(self, transaction: BookedTransaction, **kwargs) -> PositionProcessingResult:
        self.calls.append(f"position:{transaction.transaction_id}")
        self.rebuild_existing_calls.append(bool(kwargs.get("rebuild_existing", False)))
        if transaction.transaction_id == self.error_on:
            raise RuntimeError("position failed")
        return PositionProcessingResult(
            position_record_count=1,
            replay_queued=transaction.transaction_id.endswith("-2"),
            cashflow_rebuild_transactions=self.cashflow_rebuild_transactions_by_id.get(
                transaction.transaction_id,
                (),
            ),
            locked_state_epoch=self.locked_state_epoch,
        )


class _Readiness:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    async def register_processed_transactions(
        self,
        transactions: tuple[BookedTransaction, ...],
        **_kwargs,
    ) -> None:
        for transaction in transactions:
            self.calls.append(f"readiness:{transaction.transaction_id}:{transaction.epoch or 0}")


class _UnitOfWork:
    def __init__(
        self,
        *,
        calls: list[str],
        idempotency_outcome: TransactionIdempotencyOutcome = (
            TransactionIdempotencyOutcome.CLAIMED
        ),
        cost_result: CostProcessingResult | None = None,
        cost_error: Exception | None = None,
        cashflow_error: Exception | None = None,
        position_error_on: str | None = None,
        cashflow_rebuild_transactions_by_id: dict[str, tuple[BookedTransaction, ...]] | None = None,
        position_locked_state_epoch: int | None = None,
    ) -> None:
        self.calls = calls
        self.idempotency = _Idempotency(calls, outcome=idempotency_outcome)
        self.cost = _Cost(
            calls,
            result=cost_result or CostProcessingResult((_transaction(),)),
            error=cost_error,
        )
        self.cashflow = _Cashflow(calls, error=cashflow_error)
        self.position = _Position(
            calls,
            error_on=position_error_on,
            cashflow_rebuild_transactions_by_id=cashflow_rebuild_transactions_by_id,
            locked_state_epoch=position_locked_state_epoch,
        )
        self.readiness = _Readiness(calls)
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> _UnitOfWork:
        self.calls.append("enter")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        if exc_type is not None or not self.committed:
            self.rolled_back = True
            self.calls.append("rollback")

    async def commit(self) -> None:
        self.committed = True
        self.calls.append("commit")


@pytest.mark.asyncio
async def test_use_case_processes_cost_cashflow_and_each_position_leg_atomically() -> None:
    calls: list[str] = []
    first = _transaction("TX-001-1")
    second = replace(_transaction("TX-001-2"), security_id="SEC-002")
    unit_of_work = _UnitOfWork(
        calls=calls,
        cost_result=CostProcessingResult(
            processed_transactions=(first, second),
            instrument_update_count=2,
        ),
    )

    observer = _RecordingObserver()
    result = await ProcessTransactionUseCase(
        lambda: unit_of_work,
        observer=observer,
    ).execute(_command())

    assert calls == [
        "enter",
        "idempotency",
        "cost:TX-001",
        "position:TX-001-1",
        "position:TX-001-2",
        "cashflow:TX-001-1:0",
        "cashflow:TX-001-2:0",
        "readiness:TX-001-1:0",
        "readiness:TX-001-2:0",
        "commit",
    ]
    assert result.status is TransactionProcessingStatus.PROCESSED
    assert result.processed_transaction_ids == ("TX-001-1", "TX-001-2")
    assert result.instrument_update_count == 2
    assert result.cashflow_record_count == 2
    assert result.position_record_count == 2
    assert result.replay_queued_count == 1
    assert unit_of_work.rolled_back is False
    assert observer.records == [
        (
            TransactionProcessingOperation.IDEMPOTENCY,
            TransactionProcessingOutcome.SUCCEEDED,
        ),
        (TransactionProcessingOperation.COST, TransactionProcessingOutcome.SUCCEEDED),
        (TransactionProcessingOperation.POSITION, TransactionProcessingOutcome.SUCCEEDED),
        (TransactionProcessingOperation.POSITION, TransactionProcessingOutcome.SUCCEEDED),
        (
            TransactionProcessingOperation.CASHFLOW,
            TransactionProcessingOutcome.SUCCEEDED,
        ),
        (
            TransactionProcessingOperation.CASHFLOW,
            TransactionProcessingOutcome.SUCCEEDED,
        ),
        (
            TransactionProcessingOperation.PIPELINE,
            TransactionProcessingOutcome.SUCCEEDED,
        ),
        (TransactionProcessingOperation.COMMIT, TransactionProcessingOutcome.SUCCEEDED),
        (
            TransactionProcessingOperation.TRANSACTION,
            TransactionProcessingOutcome.PROCESSED,
        ),
    ]


@pytest.mark.asyncio
async def test_use_case_stages_cashflows_from_inline_position_rebuild_epoch() -> None:
    calls: list[str] = []
    incoming = replace(
        _transaction("TX-BACKDATED-COST-OUTPUT"),
        transaction_type="DIVIDEND",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("100"),
        withholding_tax_amount=Decimal("10"),
        trade_fee=Decimal("2"),
        cash_entry_mode="AUTO_GENERATE",
        settlement_cash_account_id="CASH-SGD",
        settlement_cash_instrument_id="CASH-SGD",
    )
    rebuilt_incoming = replace(incoming, epoch=3)
    rebuilt_suffix = replace(
        incoming,
        transaction_id="TX-LATER",
        transaction_date=datetime(2026, 4, 12, 9, 30, tzinfo=timezone.utc),
        gross_transaction_amount=Decimal("50"),
        epoch=3,
    )
    unit_of_work = _UnitOfWork(
        calls=calls,
        cost_result=CostProcessingResult(processed_transactions=(incoming,)),
        cashflow_rebuild_transactions_by_id={
            incoming.transaction_id: (rebuilt_incoming, rebuilt_suffix),
        },
    )
    command_transaction = replace(incoming, transaction_id="TX-BACKDATED-COMMAND")

    result = await ProcessTransactionUseCase(
        lambda: unit_of_work,
        observer=_RecordingObserver(),
    ).execute(replace(_command(), transaction=command_transaction))

    assert calls == [
        "enter",
        "idempotency",
        "cost:TX-BACKDATED-COMMAND",
        "position:TX-BACKDATED-COST-OUTPUT",
        "cashflow:TX-BACKDATED-COST-OUTPUT:3",
        "cashflow:TX-LATER:3",
        "readiness:TX-BACKDATED-COST-OUTPUT:3",
        "readiness:TX-LATER:3",
        "commit",
    ]
    assert result.processed_transaction_ids == ("TX-BACKDATED-COST-OUTPUT",)
    assert result.cashflow_record_count == 2
    assert result.position_record_count == 1
    assert unit_of_work.cashflow.calculation_contexts == [
        CashflowCalculationContext.CURRENT_BOOKING,
        CashflowCalculationContext.HISTORICAL_REBUILD,
    ]
    rule = CashflowRule(
        classification=CashflowClassification.INCOME,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )
    cashflow_amounts = [
        calculate_transaction_cashflow(
            cashflow_transaction,
            rule,
            calculation_context=calculation_context,
        ).amount
        for cashflow_transaction, calculation_context in zip(
            unit_of_work.cashflow.transactions,
            unit_of_work.cashflow.calculation_contexts,
            strict=True,
        )
        if calculation_context is not None
    ]
    assert cashflow_amounts == [Decimal("88"), Decimal("38")]
    assert (
        build_generated_settlement_cash_leg(rebuilt_incoming).gross_transaction_amount
        == (cashflow_amounts[0])
    )
    assert (
        build_generated_settlement_cash_leg(rebuilt_suffix).gross_transaction_amount
        == (cashflow_amounts[1])
    )


@pytest.mark.asyncio
async def test_use_case_reuses_write_locked_position_epoch_for_cashflow_fence() -> None:
    calls: list[str] = []
    unit_of_work = _UnitOfWork(calls=calls, position_locked_state_epoch=3)

    await ProcessTransactionUseCase(
        lambda: unit_of_work,
        observer=_RecordingObserver(),
    ).execute(_command())

    assert unit_of_work.cashflow.locked_position_epochs == [3]


@pytest.mark.asyncio
async def test_use_case_suppresses_duplicate_without_running_modules_or_commit() -> None:
    calls: list[str] = []
    unit_of_work = _UnitOfWork(
        calls=calls,
        idempotency_outcome=TransactionIdempotencyOutcome.PHYSICAL_DUPLICATE,
    )

    observer = _RecordingObserver()
    result = await ProcessTransactionUseCase(
        lambda: unit_of_work,
        observer=observer,
    ).execute(_command())

    assert calls == ["enter", "idempotency", "rollback"]
    assert result.status is TransactionProcessingStatus.DUPLICATE
    assert unit_of_work.committed is False
    assert observer.records[-1] == (
        TransactionProcessingOperation.TRANSACTION,
        TransactionProcessingOutcome.DUPLICATE,
    )
    assert observer.records[0] == (
        TransactionProcessingOperation.IDEMPOTENCY,
        TransactionProcessingOutcome.PHYSICAL_DUPLICATE,
    )


@pytest.mark.asyncio
async def test_use_case_suppresses_semantic_duplicate_from_another_physical_event() -> None:
    calls: list[str] = []
    unit_of_work = _UnitOfWork(
        calls=calls,
        idempotency_outcome=TransactionIdempotencyOutcome.SEMANTIC_DUPLICATE,
    )
    observer = _RecordingObserver()

    result = await ProcessTransactionUseCase(
        lambda: unit_of_work,
        observer=observer,
    ).execute(_command())

    assert result.status is TransactionProcessingStatus.DUPLICATE
    assert calls == ["enter", "idempotency", "rollback"]
    assert observer.records[0] == (
        TransactionProcessingOperation.IDEMPOTENCY,
        TransactionProcessingOutcome.SEMANTIC_DUPLICATE,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "idempotency_outcome",
    [
        TransactionIdempotencyOutcome.PHYSICAL_DUPLICATE,
        TransactionIdempotencyOutcome.SEMANTIC_DUPLICATE,
    ],
)
async def test_use_case_acknowledges_historical_fee_dominated_duplicates(
    idempotency_outcome: TransactionIdempotencyOutcome,
) -> None:
    calls: list[str] = []
    unit_of_work = _UnitOfWork(
        calls=calls,
        idempotency_outcome=idempotency_outcome,
    )
    command = replace(
        _command(),
        transaction=replace(
            _command().transaction,
            transaction_type="SELL",
            gross_transaction_amount=Decimal("100"),
            trade_fee=Decimal("100"),
        ),
    )

    result = await ProcessTransactionUseCase(
        lambda: unit_of_work,
        observer=_RecordingObserver(),
    ).execute(command)

    assert result.status is TransactionProcessingStatus.DUPLICATE
    assert calls == ["enter", "idempotency", "rollback"]


@pytest.mark.asyncio
async def test_use_case_reprocesses_semantic_duplicate_with_canonical_repair_intent() -> None:
    calls: list[str] = []
    unit_of_work = _UnitOfWork(
        calls=calls,
        idempotency_outcome=TransactionIdempotencyOutcome.SEMANTIC_DUPLICATE,
    )
    command = replace(
        _command(),
        metadata=replace(
            _command().metadata,
            processing_intent=TransactionProcessingIntent.REPAIR,
        ),
    )

    observer = _RecordingObserver()
    result = await ProcessTransactionUseCase(
        lambda: unit_of_work,
        observer=observer,
    ).execute(command)

    assert result.status is TransactionProcessingStatus.PROCESSED
    assert calls == [
        "enter",
        "idempotency",
        "repair-idempotency",
        "cost:TX-001",
        "position:TX-001",
        "cashflow:TX-001:0",
        "readiness:TX-001:0",
        "commit",
    ]
    assert observer.records[0] == (
        TransactionProcessingOperation.IDEMPOTENCY,
        TransactionProcessingOutcome.REPLAYED,
    )


@pytest.mark.asyncio
async def test_use_case_suppresses_redelivered_canonical_repair() -> None:
    calls: list[str] = []
    unit_of_work = _UnitOfWork(
        calls=calls,
        idempotency_outcome=TransactionIdempotencyOutcome.SEMANTIC_DUPLICATE,
    )
    unit_of_work.idempotency.repair_claimed = False
    command = replace(
        _command(),
        metadata=replace(
            _command().metadata,
            processing_intent=TransactionProcessingIntent.REPAIR,
        ),
    )

    result = await ProcessTransactionUseCase(
        lambda: unit_of_work,
        observer=_RecordingObserver(),
    ).execute(command)

    assert result.status is TransactionProcessingStatus.DUPLICATE
    assert calls == ["enter", "idempotency", "repair-idempotency", "rollback"]


@pytest.mark.asyncio
async def test_use_case_rejects_material_semantic_conflict_before_financial_work() -> None:
    calls: list[str] = []
    unit_of_work = _UnitOfWork(
        calls=calls,
        idempotency_outcome=TransactionIdempotencyOutcome.SEMANTIC_CONFLICT,
    )
    observer = _RecordingObserver()

    with pytest.raises(TransactionProcessingRejected) as exc_info:
        await ProcessTransactionUseCase(
            lambda: unit_of_work,
            observer=observer,
        ).execute(_command())

    assert exc_info.value.reason_code == "transaction_semantic_conflict"
    assert exc_info.value.retryable is False
    assert calls == ["enter", "idempotency", "rollback"]
    assert observer.records[0] == (
        TransactionProcessingOperation.IDEMPOTENCY,
        TransactionProcessingOutcome.SEMANTIC_CONFLICT,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "transaction_type",
        "gross_amount",
        "fee_amount",
        "withholding_tax_amount",
        "reason_code",
        "expected_field",
        "expected_available_proceeds",
        "expected_net_settlement",
    ),
    [
        (
            "SELL",
            "100",
            "100",
            None,
            "SELL_010_NON_POSITIVE_NET_SETTLEMENT",
            "trade_fee",
            "100",
            "0",
        ),
        (
            "DIVIDEND",
            "100",
            "0",
            "100",
            "DIVIDEND_013_NON_POSITIVE_NET_SETTLEMENT",
            "withholding_tax_amount",
            "0",
            "0",
        ),
        (
            "DIVIDEND",
            "100",
            "0",
            "100.01",
            "DIVIDEND_015_WITHHOLDING_EXCEEDS_GROSS_AMOUNT",
            "withholding_tax_amount",
            "-0.01",
            "-0.01",
        ),
        (
            "DIVIDEND",
            "100",
            "0.01",
            "-0.01",
            "DIVIDEND_014_NEGATIVE_WITHHOLDING_TAX",
            "withholding_tax_amount",
            "100.01",
            "100.00",
        ),
        (
            "INTEREST",
            "10",
            "8",
            "2",
            "INTEREST_017_NON_POSITIVE_NET_SETTLEMENT",
            "trade_fee",
            "8",
            "0",
        ),
    ],
)
async def test_use_case_rejects_invalid_settlement_economics_before_financial_work(
    transaction_type: str,
    gross_amount: str,
    fee_amount: str,
    withholding_tax_amount: str | None,
    reason_code: str,
    expected_field: str,
    expected_available_proceeds: str,
    expected_net_settlement: str,
) -> None:
    calls: list[str] = []
    unit_of_work = _UnitOfWork(calls=calls)
    transaction = replace(
        _transaction(),
        transaction_type=transaction_type,
        gross_transaction_amount=Decimal(gross_amount),
        trade_fee=Decimal(fee_amount),
        withholding_tax_amount=(
            Decimal(withholding_tax_amount) if withholding_tax_amount is not None else None
        ),
        interest_direction=("INCOME" if transaction_type == "INTEREST" else None),
    )
    command = replace(_command(), transaction=transaction)
    observer = _RecordingObserver()

    with pytest.raises(TransactionProcessingRejected) as raised:
        await ProcessTransactionUseCase(
            lambda: unit_of_work,
            observer=observer,
        ).execute(command)

    assert raised.value.reason_code == reason_code
    assert raised.value.retryable is False
    assert raised.value.detail == {
        "portfolio_id": "PB-001",
        "transaction_id": "TX-001",
        "transaction_type": transaction_type,
        "field": expected_field,
        "available_proceeds": expected_available_proceeds,
        "fee_amount": fee_amount,
        "net_settlement_amount": expected_net_settlement,
    }
    assert calls == ["enter", "idempotency", "rollback"]
    assert observer.records == [
        (
            TransactionProcessingOperation.IDEMPOTENCY,
            TransactionProcessingOutcome.SUCCEEDED,
        ),
        (
            TransactionProcessingOperation.TRANSACTION,
            TransactionProcessingOutcome.REJECTED,
        ),
    ]


@pytest.mark.asyncio
async def test_use_case_rejects_mismatched_interest_net_before_financial_work() -> None:
    calls: list[str] = []
    unit_of_work = _UnitOfWork(calls=calls)
    command = replace(
        _command(),
        transaction=replace(
            _transaction(),
            transaction_type="INTEREST",
            gross_transaction_amount=Decimal("10"),
            withholding_tax_amount=Decimal("2"),
            net_interest_amount=Decimal("100"),
            interest_direction="INCOME",
            trade_fee=Decimal("50"),
        ),
    )

    with pytest.raises(TransactionProcessingRejected) as raised:
        await ProcessTransactionUseCase(
            lambda: unit_of_work,
            observer=_RecordingObserver(),
        ).execute(command)

    assert raised.value.reason_code == "INTEREST_015_NET_RECONCILIATION_MISMATCH"
    assert raised.value.detail == {
        "portfolio_id": "PB-001",
        "transaction_id": "TX-001",
        "transaction_type": "INTEREST",
        "field": "net_interest_amount",
        "available_proceeds": "8",
        "fee_amount": "50",
        "net_settlement_amount": "-42",
    }
    assert calls == ["enter", "idempotency", "rollback"]


@pytest.mark.asyncio
async def test_repair_intent_claims_payload_specific_correction_identity() -> None:
    calls: list[str] = []
    unit_of_work = _UnitOfWork(
        calls=calls,
        idempotency_outcome=TransactionIdempotencyOutcome.SEMANTIC_CONFLICT,
    )
    unit_of_work.idempotency.outcomes.append(TransactionIdempotencyOutcome.CLAIMED)
    command = replace(
        _command(),
        transaction=replace(
            _command().transaction,
            quantity=Decimal("12"),
            gross_transaction_amount=Decimal("306"),
        ),
        metadata=replace(
            _command().metadata,
            processing_intent=TransactionProcessingIntent.REPAIR,
        ),
    )

    result = await ProcessTransactionUseCase(
        lambda: unit_of_work,
        observer=_RecordingObserver(),
    ).execute(command)

    assert result.status is TransactionProcessingStatus.PROCESSED
    assert calls == [
        "enter",
        "idempotency",
        "idempotency",
        "cost:TX-001",
        "position:TX-001",
        "cashflow:TX-001:0",
        "readiness:TX-001:0",
        "commit",
    ]
    assert unit_of_work.idempotency.claim_kwargs["semantic_key"].startswith(
        "transaction-correction:v1:PB-001:TX-001:0:sha256:"
    )
    assert unit_of_work.position.rebuild_existing_calls == [True]


@pytest.mark.asyncio
async def test_repair_intent_fails_closed_when_correction_identity_conflicts() -> None:
    calls: list[str] = []
    unit_of_work = _UnitOfWork(
        calls=calls,
        idempotency_outcome=TransactionIdempotencyOutcome.SEMANTIC_CONFLICT,
    )
    command = replace(
        _command(),
        metadata=replace(
            _command().metadata,
            processing_intent=TransactionProcessingIntent.REPAIR,
        ),
    )

    with pytest.raises(TransactionProcessingRejected) as exc_info:
        await ProcessTransactionUseCase(
            lambda: unit_of_work,
            observer=_RecordingObserver(),
        ).execute(command)

    assert exc_info.value.reason_code == "transaction_semantic_conflict"
    assert calls == ["enter", "idempotency", "idempotency", "rollback"]


@pytest.mark.asyncio
async def test_use_case_claims_versioned_domain_identity() -> None:
    calls: list[str] = []
    unit_of_work = _UnitOfWork(calls=calls)

    await ProcessTransactionUseCase(
        lambda: unit_of_work,
        observer=_RecordingObserver(),
    ).execute(_command())

    assert unit_of_work.idempotency.claim_kwargs["semantic_key"] == (
        "transaction-processing:v1:PB-001:TX-001:0"
    )
    assert unit_of_work.idempotency.claim_kwargs["payload_fingerprint"].startswith("sha256:")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure_kwargs", "expected_calls"),
    [
        (
            {"cost_error": RuntimeError("cost failed")},
            ["enter", "idempotency", "cost:TX-001", "rollback"],
        ),
        (
            {"cashflow_error": RuntimeError("cashflow failed")},
            [
                "enter",
                "idempotency",
                "cost:TX-001",
                "position:TX-001",
                "cashflow:TX-001:0",
                "rollback",
            ],
        ),
        (
            {"position_error_on": "TX-001"},
            [
                "enter",
                "idempotency",
                "cost:TX-001",
                "position:TX-001",
                "rollback",
            ],
        ),
    ],
)
async def test_use_case_rolls_back_complete_unit_of_work_on_module_failure(
    failure_kwargs,
    expected_calls,
) -> None:
    calls: list[str] = []
    unit_of_work = _UnitOfWork(calls=calls, **failure_kwargs)
    observer = _RecordingObserver()

    with pytest.raises(RuntimeError):
        await ProcessTransactionUseCase(
            lambda: unit_of_work,
            observer=observer,
        ).execute(_command())

    assert calls == expected_calls
    assert unit_of_work.committed is False
    assert unit_of_work.rolled_back is True
    assert observer.records[-1] == (
        TransactionProcessingOperation.TRANSACTION,
        TransactionProcessingOutcome.FAILED,
    )
