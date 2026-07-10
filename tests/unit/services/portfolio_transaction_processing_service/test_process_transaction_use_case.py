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
    TransactionProcessingStatus,
)
from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.ports import (
    CashflowProcessingResult,
    CostProcessingResult,
    PositionProcessingResult,
)


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
    def __init__(self, calls: list[str], *, claimed: bool = True) -> None:
        self.calls = calls
        self.claimed = claimed

    async def claim(self, **_kwargs) -> bool:
        self.calls.append("idempotency")
        return self.claimed


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

    async def process(self, transaction: BookedTransaction, **_kwargs) -> CashflowProcessingResult:
        self.calls.append(f"cashflow:{transaction.transaction_id}")
        if self.error is not None:
            raise self.error
        return CashflowProcessingResult(cashflow_record_count=1)


class _Position:
    def __init__(self, calls: list[str], *, error_on: str | None = None) -> None:
        self.calls = calls
        self.error_on = error_on

    async def process(self, transaction: BookedTransaction, **_kwargs) -> PositionProcessingResult:
        self.calls.append(f"position:{transaction.transaction_id}")
        if transaction.transaction_id == self.error_on:
            raise RuntimeError("position failed")
        return PositionProcessingResult(
            position_record_count=1,
            replay_queued=transaction.transaction_id.endswith("-2"),
        )


class _UnitOfWork:
    def __init__(
        self,
        *,
        calls: list[str],
        claimed: bool = True,
        cost_result: CostProcessingResult | None = None,
        cost_error: Exception | None = None,
        cashflow_error: Exception | None = None,
        position_error_on: str | None = None,
    ) -> None:
        self.calls = calls
        self.idempotency = _Idempotency(calls, claimed=claimed)
        self.cost = _Cost(
            calls,
            result=cost_result or CostProcessingResult((_transaction(),)),
            error=cost_error,
        )
        self.cashflow = _Cashflow(calls, error=cashflow_error)
        self.position = _Position(calls, error_on=position_error_on)
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

    result = await ProcessTransactionUseCase(lambda: unit_of_work).execute(_command())

    assert calls == [
        "enter",
        "idempotency",
        "cost:TX-001",
        "cashflow:TX-001",
        "position:TX-001-1",
        "position:TX-001-2",
        "commit",
    ]
    assert result.status is TransactionProcessingStatus.PROCESSED
    assert result.processed_transaction_ids == ("TX-001-1", "TX-001-2")
    assert result.instrument_update_count == 2
    assert result.cashflow_record_count == 1
    assert result.position_record_count == 2
    assert result.replay_queued_count == 1
    assert unit_of_work.rolled_back is False


@pytest.mark.asyncio
async def test_use_case_suppresses_duplicate_without_running_modules_or_commit() -> None:
    calls: list[str] = []
    unit_of_work = _UnitOfWork(calls=calls, claimed=False)

    result = await ProcessTransactionUseCase(lambda: unit_of_work).execute(_command())

    assert calls == ["enter", "idempotency", "rollback"]
    assert result.status is TransactionProcessingStatus.DUPLICATE
    assert unit_of_work.committed is False


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
                "cashflow:TX-001",
                "rollback",
            ],
        ),
        (
            {"position_error_on": "TX-001"},
            [
                "enter",
                "idempotency",
                "cost:TX-001",
                "cashflow:TX-001",
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

    with pytest.raises(RuntimeError):
        await ProcessTransactionUseCase(lambda: unit_of_work).execute(_command())

    assert calls == expected_calls
    assert unit_of_work.committed is False
    assert unit_of_work.rolled_back is True
