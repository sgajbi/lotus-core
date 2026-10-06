"""Borrowed-UOW storage port for immutable transaction source confirmation."""

from dataclasses import dataclass
from typing import Protocol

from portfolio_common.database_models import OutboxEvent, Transaction, TransactionSourceRevision


@dataclass(frozen=True, slots=True)
class RetainedSourceRows:
    transaction: Transaction
    raw_event: OutboxEvent
    head: TransactionSourceRevision | None


class TransactionSourceRevisionPort(Protocol):
    async def committed_command(
        self, *, tenant_id: str, command_id: str
    ) -> TransactionSourceRevision | None: ...

    async def read_committed_source(
        self, revision: TransactionSourceRevision
    ) -> RetainedSourceRows: ...

    async def lock_admitted_operation(
        self, *, tenant_id: str, operation_id: str, command_id: str
    ) -> OutboxEvent: ...

    async def lock_retained_source(
        self, *, tenant_id: str, transaction_id: str
    ) -> RetainedSourceRows: ...

    async def stage_revision_and_notification(
        self, revision: TransactionSourceRevision
    ) -> None: ...
