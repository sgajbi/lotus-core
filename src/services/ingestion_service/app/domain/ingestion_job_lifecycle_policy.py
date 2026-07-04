from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class IngestionJobStatus(StrEnum):
    ACCEPTED = "accepted"
    QUEUED = "queued"
    FAILED = "failed"


class IngestionJobTransition(StrEnum):
    ACCEPTED_TO_QUEUED = "accepted_to_queued"
    MARK_FAILED = "mark_failed"
    MARK_RETRIED = "mark_retried"
    RETRY_TO_QUEUED = "retry_to_queued"


@dataclass(frozen=True, slots=True)
class IngestionJobTransitionRule:
    transition: IngestionJobTransition
    expected_statuses: tuple[str, ...]
    target_status: str | None
    failure_evidence_required: bool = False
    replay_audit_required: bool = False
    retry_metadata_required: bool = False

    def allows(self, current_status: str) -> bool:
        return current_status in self.expected_statuses


KNOWN_INGESTION_JOB_STATUSES = frozenset(status.value for status in IngestionJobStatus)
INGESTION_JOB_TERMINAL_STATUSES: frozenset[str] = frozenset()


INGESTION_JOB_TRANSITION_RULES: dict[IngestionJobTransition, IngestionJobTransitionRule] = {
    IngestionJobTransition.ACCEPTED_TO_QUEUED: IngestionJobTransitionRule(
        transition=IngestionJobTransition.ACCEPTED_TO_QUEUED,
        expected_statuses=(IngestionJobStatus.ACCEPTED.value,),
        target_status=IngestionJobStatus.QUEUED.value,
    ),
    IngestionJobTransition.MARK_FAILED: IngestionJobTransitionRule(
        transition=IngestionJobTransition.MARK_FAILED,
        expected_statuses=(
            IngestionJobStatus.ACCEPTED.value,
            IngestionJobStatus.FAILED.value,
        ),
        target_status=IngestionJobStatus.FAILED.value,
        failure_evidence_required=True,
    ),
    IngestionJobTransition.MARK_RETRIED: IngestionJobTransitionRule(
        transition=IngestionJobTransition.MARK_RETRIED,
        expected_statuses=(
            IngestionJobStatus.FAILED.value,
            IngestionJobStatus.ACCEPTED.value,
            IngestionJobStatus.QUEUED.value,
        ),
        target_status=None,
        replay_audit_required=True,
        retry_metadata_required=True,
    ),
    IngestionJobTransition.RETRY_TO_QUEUED: IngestionJobTransitionRule(
        transition=IngestionJobTransition.RETRY_TO_QUEUED,
        expected_statuses=(
            IngestionJobStatus.FAILED.value,
            IngestionJobStatus.ACCEPTED.value,
            IngestionJobStatus.QUEUED.value,
        ),
        target_status=IngestionJobStatus.QUEUED.value,
        replay_audit_required=True,
        retry_metadata_required=True,
    ),
}


def ingestion_job_transition_rule(
    transition: IngestionJobTransition,
) -> IngestionJobTransitionRule:
    return INGESTION_JOB_TRANSITION_RULES[transition]


def ingestion_job_transition_expected_statuses(
    transition: IngestionJobTransition,
) -> tuple[str, ...]:
    return ingestion_job_transition_rule(transition).expected_statuses


def ingestion_job_transition_allowed(
    *,
    transition: IngestionJobTransition,
    current_status: str,
) -> bool:
    return ingestion_job_transition_rule(transition).allows(current_status)


def ingestion_job_status_is_terminal(status: str) -> bool:
    return status in INGESTION_JOB_TERMINAL_STATUSES
