from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from types import TracebackType
from typing import Protocol, Self

from ..domain import BookedTransaction, build_transaction_semantic_identity
from ..domain.cashflow import CashflowCalculationContext
from .position_history import AdmittedPositionCorrectionGroup, MaterializedPositionReceipt


@dataclass(frozen=True, slots=True)
class FirstPublicationSourceAuthority:
    """Exact original input qualified under source locks in the current UOW."""

    tenant_id: str
    portfolio_id: str
    security_id: str
    transaction_id: str
    payload_fingerprint: str

    def matches(self, transaction: BookedTransaction) -> bool:
        """Bind tenant separately from the full original material fingerprint."""
        return transaction.epoch is None and (
            self.tenant_id,
            self.portfolio_id,
            self.security_id,
            self.transaction_id,
            self.payload_fingerprint,
        ) == (
            transaction.tenant_id,
            transaction.portfolio_id,
            transaction.security_id,
            transaction.transaction_id,
            build_transaction_semantic_identity(transaction).payload_fingerprint,
        )


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
    processed_transaction_quantity: Decimal | None = None
    materialized_receipt: MaterializedPositionReceipt | None = None


class TransactionIdempotencyOutcome(StrEnum):
    CLAIMED = "claimed"
    PHYSICAL_DUPLICATE = "physical_duplicate"
    SEMANTIC_DUPLICATE = "semantic_duplicate"
    SEMANTIC_CONFLICT = "semantic_conflict"


class TransactionIdempotencyPort(Protocol):
    async def claim(
        self,
        *,
        tenant_id: str,
        event_id: str,
        portfolio_id: str,
        semantic_key: str,
        payload_fingerprint: str,
        correlation_id: str | None,
    ) -> TransactionIdempotencyOutcome: ...

    async def matches_existing_claim(
        self,
        *,
        tenant_id: str,
        event_id: str,
        portfolio_id: str,
        semantic_key: str,
        payload_fingerprint: str,
    ) -> bool: ...

    async def claim_repair_delivery(
        self,
        *,
        tenant_id: str,
        event_id: str,
        portfolio_id: str,
        correlation_id: str | None,
    ) -> bool: ...


class CostProcessingPort(Protocol):
    async def load_first_publication_source(
        self, transaction: BookedTransaction
    ) -> FirstPublicationSourceAuthority | None:
        """Qualify optional ordinary source authority before any cost writes."""
        ...

    async def load_derived_financial_transaction(
        self, transaction: BookedTransaction
    ) -> BookedTransaction | None: ...

    async def validate_unversioned_repair_source(self, transaction: BookedTransaction) -> None:
        """Retain canonical source authority in the caller's UOW before cost writes."""
        ...

    async def process(
        self,
        transaction: BookedTransaction,
        *,
        correlation_id: str | None,
        traceparent: str | None,
        reconcile_superseded_derived: bool = False,
    ) -> CostProcessingResult: ...


class CashflowProcessingPort(Protocol):
    async def has_materialized_effect(
        self, transaction: BookedTransaction, *, locked_position_epoch: int
    ) -> bool:
        """Qualify existing financial effects without creating a receipt or ledger row."""
        ...

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
        admitted_correction: AdmittedPositionCorrectionGroup | None = None,
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
