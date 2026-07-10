from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Protocol, Self

from ..domain import BookedTransaction


@dataclass(frozen=True, slots=True)
class CostProcessingResult:
    processed_transactions: tuple[BookedTransaction, ...]
    instrument_update_count: int = 0


@dataclass(frozen=True, slots=True)
class CashflowProcessingResult:
    cashflow_record_count: int = 0


@dataclass(frozen=True, slots=True)
class PositionProcessingResult:
    position_record_count: int = 0
    replay_queued: bool = False


class TransactionIdempotencyPort(Protocol):
    async def claim(
        self,
        *,
        event_id: str,
        portfolio_id: str,
        correlation_id: str | None,
    ) -> bool: ...


class CostProcessingPort(Protocol):
    async def process(
        self,
        transaction: BookedTransaction,
        *,
        correlation_id: str | None,
        traceparent: str | None,
    ) -> CostProcessingResult: ...


class CashflowProcessingPort(Protocol):
    async def process(
        self,
        transaction: BookedTransaction,
        *,
        correlation_id: str | None,
        traceparent: str | None,
    ) -> CashflowProcessingResult: ...


class PositionProcessingPort(Protocol):
    async def process(
        self,
        transaction: BookedTransaction,
        *,
        correlation_id: str | None,
        traceparent: str | None,
    ) -> PositionProcessingResult: ...


class TransactionProcessingUnitOfWork(Protocol):
    idempotency: TransactionIdempotencyPort
    cost: CostProcessingPort
    cashflow: CashflowProcessingPort
    position: PositionProcessingPort

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


TransactionProcessingUnitOfWorkFactory = Callable[[], TransactionProcessingUnitOfWork]
