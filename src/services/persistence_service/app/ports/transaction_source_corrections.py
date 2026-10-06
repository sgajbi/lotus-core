"""Borrowed-UOW storage port for immutable transaction source confirmation."""

from collections.abc import Mapping
from typing import Protocol

from portfolio_common.event_contracts import TransactionSourceCorrectionRequestedEvent

from .transaction_source_facts import RetainedSourceRows, SourceOperationIntent, SourceRevisionFact


class TransactionSourceRevisionPort(Protocol):
    def normalize_command(
        self, command: TransactionSourceCorrectionRequestedEvent
    ) -> TransactionSourceCorrectionRequestedEvent: ...

    def decode_admitted_intent(
        self, payload: object
    ) -> TransactionSourceCorrectionRequestedEvent: ...

    def validate_retained_input(self, payload: Mapping[str, object]) -> None: ...

    async def committed_command(
        self, *, tenant_id: str, command_id: str
    ) -> SourceRevisionFact | None: ...

    async def read_committed_source(self, revision: SourceRevisionFact) -> RetainedSourceRows: ...

    async def lock_admitted_operation(
        self, *, tenant_id: str, operation_id: str, command_id: str
    ) -> SourceOperationIntent: ...

    async def lock_retained_source(
        self, *, tenant_id: str, transaction_id: str
    ) -> RetainedSourceRows: ...

    async def stage_revision_and_notification(self, revision: SourceRevisionFact) -> None: ...
