from services.financial_reconciliation_service.app.domain import (
    reconciliation_run_lifecycle_policy as lifecycle,
)


def test_completion_transition_defines_source_target_and_evidence_requirements() -> None:
    assert lifecycle.COMPLETE_RECONCILIATION_RUN.name == "complete_reconciliation_run"
    assert lifecycle.COMPLETE_RECONCILIATION_RUN.source_statuses == {
        lifecycle.ReconciliationRunStatus.RUNNING
    }
    assert (
        lifecycle.COMPLETE_RECONCILIATION_RUN.target_status
        is lifecycle.ReconciliationRunStatus.COMPLETED
    )
    assert lifecycle.COMPLETE_RECONCILIATION_RUN.requires_summary is True
    assert lifecycle.COMPLETE_RECONCILIATION_RUN.requires_findings_persisted is True
    assert lifecycle.initial_reconciliation_run_status() == "RUNNING"
    assert lifecycle.completed_reconciliation_run_status() == "COMPLETED"


def test_terminal_and_retryable_reconciliation_run_statuses_are_explicit() -> None:
    assert lifecycle.is_terminal_reconciliation_run_status(" completed ") is True
    assert lifecycle.is_terminal_reconciliation_run_status("RUNNING") is False
    assert lifecycle.is_retryable_reconciliation_run_status("REQUIRES_REPLAY") is True
    assert lifecycle.is_retryable_reconciliation_run_status("FAILED") is True
    assert lifecycle.is_retryable_reconciliation_run_status("COMPLETED") is False
    assert lifecycle.ReconciliationRunStatus.normalize("not-a-status") is None


def test_automatic_bundle_outcome_requires_replay_for_error_findings() -> None:
    outcome = lifecycle.determine_automatic_bundle_outcome(
        {
            "transaction_cashflow": lifecycle.ReconciliationRunLifecycleSnapshot(
                run_id="recon-tx",
                status=lifecycle.ReconciliationRunStatus.COMPLETED,
                error_count=2,
                warning_count=1,
            ),
            "position_valuation": lifecycle.ReconciliationRunLifecycleSnapshot(
                run_id="recon-val",
                status=lifecycle.ReconciliationRunStatus.COMPLETED,
                error_count=0,
                warning_count=0,
            ),
        }
    )

    assert outcome.outcome_status == "REQUIRES_REPLAY"
    assert outcome.blocking_reconciliation_types == ["transaction_cashflow"]
    assert outcome.error_count == 2
    assert outcome.warning_count == 1


def test_automatic_bundle_outcome_escalates_failed_runs() -> None:
    outcome = lifecycle.determine_automatic_bundle_outcome(
        {
            "transaction_cashflow": lifecycle.ReconciliationRunLifecycleSnapshot(
                run_id="recon-tx",
                status=lifecycle.ReconciliationRunStatus.FAILED,
                error_count=0,
                warning_count=0,
            ),
            "timeseries_integrity": lifecycle.ReconciliationRunLifecycleSnapshot(
                run_id="recon-ts",
                status=lifecycle.ReconciliationRunStatus.COMPLETED,
                error_count=1,
                warning_count=0,
            ),
        }
    )

    assert outcome.outcome_status == "FAILED"
    assert outcome.blocking_reconciliation_types == [
        "timeseries_integrity",
        "transaction_cashflow",
    ]
    assert outcome.run_ids == {
        "transaction_cashflow": "recon-tx",
        "timeseries_integrity": "recon-ts",
    }


def test_unknown_status_does_not_hide_error_findings() -> None:
    outcome = lifecycle.determine_automatic_bundle_outcome(
        {
            "legacy_run": lifecycle.ReconciliationRunLifecycleSnapshot(
                run_id="recon-legacy",
                status=None,
                error_count=1,
                warning_count=2,
            )
        }
    )

    assert outcome.outcome_status == "REQUIRES_REPLAY"
    assert outcome.blocking_reconciliation_types == ["legacy_run"]
    assert outcome.error_count == 1
    assert outcome.warning_count == 2
