from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from src.services.ingestion_service.app.DTOs.ingestion_job_dto import (
    ConsumerDlqEventResponse,
    IngestionReplayAuditResponse,
)

RecoveryState = Literal["not_requested", "dry_run_only", "recovered", "unresolved"]


@dataclass(frozen=True, slots=True)
class ConsumerDlqRecovery:
    event_id: str
    state: RecoveryState


def derive_consumer_dlq_recovery(
    *,
    events: Iterable[ConsumerDlqEventResponse],
    replay_audits: Iterable[IngestionReplayAuditResponse],
    evidence_complete: bool,
) -> tuple[ConsumerDlqRecovery, ...]:
    """Fold newest-first durable audit rows into a recovery state for each DLQ event."""

    audits_by_event: dict[str, list[IngestionReplayAuditResponse]] = {}
    for audit in replay_audits:
        if audit.recovery_path != "consumer_dlq_replay":
            continue
        audits_by_event.setdefault(audit.event_id, []).append(audit)

    recovery: list[ConsumerDlqRecovery] = []
    for event in events:
        event_audits = audits_by_event.get(event.event_id, [])
        state = (
            _derive_complete_event_recovery(event_audits)
            if evidence_complete
            else "unresolved"
        )
        recovery.append(ConsumerDlqRecovery(event_id=event.event_id, state=state))
    return tuple(recovery)


def _derive_complete_event_recovery(
    audits: list[IngestionReplayAuditResponse],
) -> RecoveryState:
    if not audits:
        return "not_requested"

    non_dry_run_audits = [audit for audit in audits if audit.replay_status != "dry_run"]
    if not non_dry_run_audits:
        return "dry_run_only"

    latest = non_dry_run_audits[0]
    if latest.replay_status == "replayed":
        return "recovered"
    if latest.replay_status != "duplicate_blocked":
        return "unresolved"

    equivalent_prior_success = any(
        audit.replay_status == "replayed"
        and audit.replay_fingerprint == latest.replay_fingerprint
        for audit in non_dry_run_audits[1:]
    )
    return "recovered" if equivalent_prior_success else "unresolved"
