from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from types import TracebackType
from typing import Protocol, Self

from ..domain import BookedTransaction
from ..domain.cashflow import CashflowCalculationContext


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
    cashflow_rebuild_transactions: tuple[BookedTransaction, ...] = ()
    locked_state_epoch: int | None = None


class TransactionIdempotencyOutcome(StrEnum):
    CLAIMED = "claimed"
    PHYSICAL_DUPLICATE = "physical_duplicate"
    SEMANTIC_DUPLICATE = "semantic_duplicate"
    SEMANTIC_CONFLICT = "semantic_conflict"


class TransactionIdempotencyPort(Protocol):
    async def claim(
        self,
        *,
        event_id: str,
        portfolio_id: str,
        semantic_key: str,
        payload_fingerprint: str,
        correlation_id: str | None,
    ) -> TransactionIdempotencyOutcome: ...

    async def claim_repair_delivery(
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
        repair_existing: bool = False,
        locked_position_epoch: int | None = None,
        calculation_context: CashflowCalculationContext = (
            CashflowCalculationContext.CURRENT_BOOKING
        ),
    ) -> CashflowProcessingResult: ...


class PositionProcessingPort(Protocol):
    async def process(
        self,
        transaction: BookedTransaction,
        *,
        correlation_id: str | None,
        traceparent: str | None,
        rebuild_existing: bool = False,
    ) -> PositionProcessingResult: ...


class TransactionReadinessProcessingPort(Protocol):
    async def register_processed_transactions(
        self,
        transactions: tuple[BookedTransaction, ...],
        *,
        correlation_id: str | None,
        traceparent: str | None,
    ) -> None: ...


class TransactionProcessingUnitOfWork(Protocol):
    @property
    def idempotency(self) -> TransactionIdempotencyPort: ...

    @property
    def cost(self) -> CostProcessingPort: ...

    @property
    def cashflow(self) -> CashflowProcessingPort: ...

    @property
    def position(self) -> PositionProcessingPort: ...

    @property
    def readiness(self) -> TransactionReadinessProcessingPort: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


TransactionProcessingUnitOfWorkFactory = Callable[[], TransactionProcessingUnitOfWork]
