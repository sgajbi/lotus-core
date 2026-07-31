from datetime import UTC, datetime, timedelta

import pytest

from src.services.event_replay_service.app.application.replay_recovery_policy import (
    derive_consumer_dlq_recovery,
)
from src.services.ingestion_service.app.DTOs.ingestion_job_dto import (
    ConsumerDlqEventResponse,
    IngestionReplayAuditResponse,
)

NOW = datetime(2026, 7, 31, tzinfo=UTC)


def _event(event_id: str = "dlq-001") -> ConsumerDlqEventResponse:
    return ConsumerDlqEventResponse(
        event_id=event_id,
        original_topic="transactions.raw.received",
        consumer_group="persistence-service-group",
        dlq_topic="dlq.persistence_service",
        error_reason_code="PERSISTENCE_TIMEOUT",
        error_reason="Persistence timed out.",
        observed_at=NOW,
    )


def _audit(
    status: str,
    *,
    event_id: str = "dlq-001",
    fingerprint: str = "fp-001",
    requested_at: datetime = NOW,
) -> IngestionReplayAuditResponse:
    return IngestionReplayAuditResponse(
        replay_id=f"replay-{status}-{requested_at.timestamp()}",
        recovery_path="consumer_dlq_replay",
        event_id=event_id,
        replay_fingerprint=fingerprint,
        replay_status=status,
        dry_run=status == "dry_run",
        replay_reason=status,
        requested_at=requested_at,
    )


@pytest.mark.parametrize(
    ("audits", "evidence_complete", "expected"),
    [
        ([_audit("replayed")], True, "recovered"),
        ([_audit("dry_run")], True, "dry_run_only"),
        ([_audit("duplicate_blocked")], True, "unresolved"),
        (
            [
                _audit("duplicate_blocked", requested_at=NOW + timedelta(seconds=1)),
                _audit("replayed"),
            ],
            True,
            "recovered",
        ),
        (
            [
                _audit("failed", requested_at=NOW + timedelta(seconds=1)),
                _audit("replayed"),
            ],
            True,
            "unresolved",
        ),
        ([_audit("replayed_bookkeeping_failed")], True, "unresolved"),
        ([_audit("replayed")], False, "unresolved"),
    ],
)
def test_derives_fail_closed_event_recovery(audits, evidence_complete, expected) -> None:
    result = derive_consumer_dlq_recovery(
        events=[_event()],
        replay_audits=audits,
        evidence_complete=evidence_complete,
    )

    assert result[0].state == expected


def test_folds_mixed_events_independently_and_ignores_job_retry_audits() -> None:
    job_retry = _audit("replayed", event_id="dlq-002")
    job_retry = job_retry.model_copy(
        update={"recovery_path": "ingestion_job_retry", "event_id": "job:job-001"}
    )

    result = derive_consumer_dlq_recovery(
        events=[_event("dlq-001"), _event("dlq-002")],
        replay_audits=[_audit("replayed", event_id="dlq-001"), job_retry],
        evidence_complete=True,
    )

    assert [(row.event_id, row.state) for row in result] == [
        ("dlq-001", "recovered"),
        ("dlq-002", "not_requested"),
    ]
