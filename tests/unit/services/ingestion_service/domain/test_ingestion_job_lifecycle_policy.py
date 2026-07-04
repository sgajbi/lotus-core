from src.services.ingestion_service.app.domain.ingestion_job_lifecycle_policy import (
    INGESTION_JOB_TERMINAL_STATUSES,
    KNOWN_INGESTION_JOB_STATUSES,
    IngestionJobStatus,
    IngestionJobTransition,
    ingestion_job_status_is_terminal,
    ingestion_job_transition_allowed,
    ingestion_job_transition_expected_statuses,
    ingestion_job_transition_rule,
)


def test_ingestion_job_lifecycle_declares_known_statuses() -> None:
    assert KNOWN_INGESTION_JOB_STATUSES == {"accepted", "queued", "failed"}
    assert [status.value for status in IngestionJobStatus] == [
        "accepted",
        "queued",
        "failed",
    ]


def test_accepted_to_queued_transition_policy() -> None:
    rule = ingestion_job_transition_rule(IngestionJobTransition.ACCEPTED_TO_QUEUED)

    assert rule.expected_statuses == ("accepted",)
    assert rule.target_status == "queued"
    assert not rule.failure_evidence_required
    assert not rule.replay_audit_required
    assert not rule.retry_metadata_required
    assert ingestion_job_transition_allowed(
        transition=IngestionJobTransition.ACCEPTED_TO_QUEUED,
        current_status="accepted",
    )
    assert not ingestion_job_transition_allowed(
        transition=IngestionJobTransition.ACCEPTED_TO_QUEUED,
        current_status="queued",
    )


def test_mark_failed_transition_requires_failure_evidence() -> None:
    rule = ingestion_job_transition_rule(IngestionJobTransition.MARK_FAILED)

    assert rule.expected_statuses == ("accepted", "failed")
    assert rule.target_status == "failed"
    assert rule.failure_evidence_required
    assert not rule.replay_audit_required
    assert not rule.retry_metadata_required
    assert ingestion_job_transition_allowed(
        transition=IngestionJobTransition.MARK_FAILED,
        current_status="accepted",
    )
    assert not ingestion_job_transition_allowed(
        transition=IngestionJobTransition.MARK_FAILED,
        current_status="queued",
    )


def test_retry_transitions_require_audit_and_retry_metadata() -> None:
    retry_expected_statuses = ("failed", "accepted", "queued")

    mark_retried_rule = ingestion_job_transition_rule(IngestionJobTransition.MARK_RETRIED)
    retry_to_queued_rule = ingestion_job_transition_rule(IngestionJobTransition.RETRY_TO_QUEUED)

    assert (
        ingestion_job_transition_expected_statuses(IngestionJobTransition.MARK_RETRIED)
        == retry_expected_statuses
    )
    assert mark_retried_rule.target_status is None
    assert mark_retried_rule.replay_audit_required
    assert mark_retried_rule.retry_metadata_required

    assert retry_to_queued_rule.expected_statuses == retry_expected_statuses
    assert retry_to_queued_rule.target_status == "queued"
    assert retry_to_queued_rule.replay_audit_required
    assert retry_to_queued_rule.retry_metadata_required


def test_unknown_or_terminal_statuses_are_not_mutation_sources() -> None:
    assert INGESTION_JOB_TERMINAL_STATUSES == frozenset()
    assert all(
        not ingestion_job_status_is_terminal(status) for status in KNOWN_INGESTION_JOB_STATUSES
    )
    assert not ingestion_job_transition_allowed(
        transition=IngestionJobTransition.RETRY_TO_QUEUED,
        current_status="archived",
    )
