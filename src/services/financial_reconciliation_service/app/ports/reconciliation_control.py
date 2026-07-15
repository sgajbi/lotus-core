"""Application ports for financial reconciliation completion ownership."""

from __future__ import annotations

from typing import Protocol

from ..domain.reconciliation_control import (
    FinancialReconciliationCompletion,
    RecordedReconciliationControl,
)


class ReconciliationControlEvidenceRepository(Protocol):
    """Persist authoritative reconciliation control evidence."""

    async def record_completion(
        self,
        completion: FinancialReconciliationCompletion,
    ) -> RecordedReconciliationControl: ...


class ReconciliationCompletionEventStager(Protocol):
    """Stage durable reconciliation completion and control contracts."""

    async def stage_reconciliation_completed(
        self,
        completion: FinancialReconciliationCompletion,
        *,
        correlation_id: str | None,
    ) -> None: ...

    async def stage_controls_evaluated(
        self,
        completion: FinancialReconciliationCompletion,
        *,
        status: str,
        controls_blocking: bool,
        correlation_id: str | None,
    ) -> None: ...
