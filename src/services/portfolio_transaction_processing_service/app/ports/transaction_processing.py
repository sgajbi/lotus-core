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
        event_id: str,
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
    @property
    def idempotency(self) -> TransactionIdempotencyPort: ...

    @property
    def cost(self) -> CostProcessingPort: ...

    @property
    def cashflow(self) -> CashflowProcessingPort: ...

    @property
    def position(self) -> PositionProcessingPort: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


TransactionProcessingUnitOfWorkFactory = Callable[[], TransactionProcessingUnitOfWork]
