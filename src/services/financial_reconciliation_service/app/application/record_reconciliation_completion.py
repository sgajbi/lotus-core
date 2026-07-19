"""Application use case for authoritative reconciliation completion evidence."""

from __future__ import annotations

from ..domain.reconciliation_control import (
    FinancialReconciliationCompletion,
    is_control_blocking,
    should_emit_controls_for_epoch,
)
from ..ports.reconciliation_control import (
    ReconciliationCompletionEventStager,
    ReconciliationControlEvidenceRepository,
)


class RecordFinancialReconciliationCompletion:
    """Persist control evidence and stage downstream contracts atomically."""

    def __init__(
        self,
        *,
        evidence_repository: ReconciliationControlEvidenceRepository,
        event_stager: ReconciliationCompletionEventStager,
    ) -> None:
        self._evidence_repository = evidence_repository
        self._event_stager = event_stager

    async def execute(
        self,
        completion: FinancialReconciliationCompletion,
        *,
        correlation_id: str | None,
    ) -> None:
        """Record one completion and emit controls only for the latest epoch."""

        recorded_control = await self._evidence_repository.record_completion(completion)
        if not recorded_control.accepted_revision:
            return
        await self._event_stager.stage_reconciliation_completed(
            completion,
            correlation_id=correlation_id,
        )
        if not should_emit_controls_for_epoch(
            latest_epoch=recorded_control.latest_epoch,
            completed_epoch=completion.epoch,
        ):
            return
        await self._event_stager.stage_controls_evaluated(
            completion,
            status=recorded_control.status,
            controls_blocking=is_control_blocking(recorded_control.status),
            correlation_id=correlation_id,
        )
