import json

from scripts.performance_load_gate import _evaluate_profile, _write_report


def test_evaluate_profile_uses_incremental_health_pressure_against_baseline() -> None:
    result = _evaluate_profile(
        profile_name="steady_state",
        records_submitted=100,
        batches_submitted=2,
        started_at=10.0,
        ended_at=20.0,
        baseline_health={
            "summary": {"backlog_jobs": 64},
            "slo": {"backlog_age_seconds": 1200.0},
            "error_budget": {
                "dlq_events_in_window": 118,
                "dlq_budget_events_per_window": 10,
                "replay_backlog_pressure_ratio": "0.0128",
            },
        },
        health={
            "summary": {"backlog_jobs": 68},
            "slo": {"backlog_age_seconds": 1260.0},
            "error_budget": {
                "dlq_events_in_window": 118,
                "dlq_budget_events_per_window": 10,
                "replay_backlog_pressure_ratio": "0.0131",
            },
        },
        drain_seconds=None,
        thresholds={
            "min_throughput_rps": 5.0,
            "max_backlog_age_increase_seconds": 120.0,
            "max_dlq_pressure_ratio_added": 0.5,
            "max_replay_pressure_ratio_increase": 0.01,
            "max_drain_seconds": None,
        },
    )

    assert result.checks_passed is True
    assert result.backlog_jobs_growth_during_profile == 4
    assert result.backlog_age_increase_seconds == 60.0
    assert result.dlq_events_added_during_profile == 0
    assert result.dlq_pressure_ratio_added == 0.0
    assert result.replay_pressure_ratio_increase == 0.0003


def test_evaluate_profile_fails_when_incremental_pressure_breaches_thresholds() -> None:
    result = _evaluate_profile(
        profile_name="burst",
        records_submitted=10,
        batches_submitted=1,
        started_at=10.0,
        ended_at=20.0,
        baseline_health={
            "summary": {"backlog_jobs": 8},
            "slo": {"backlog_age_seconds": 15.0},
            "error_budget": {
                "dlq_events_in_window": 2,
                "dlq_budget_events_per_window": 10,
                "replay_backlog_pressure_ratio": "0.0500",
            },
        },
        health={
            "summary": {"backlog_jobs": 18},
            "slo": {"backlog_age_seconds": 175.0},
            "error_budget": {
                "dlq_events_in_window": 9,
                "dlq_budget_events_per_window": 10,
                "replay_backlog_pressure_ratio": "0.4000",
            },
        },
        drain_seconds=None,
        thresholds={
            "min_throughput_rps": 2.0,
            "max_backlog_age_increase_seconds": 60.0,
            "max_dlq_pressure_ratio_added": 0.5,
            "max_replay_pressure_ratio_increase": 0.2,
            "max_drain_seconds": None,
        },
    )

    assert result.checks_passed is False
    assert "backlog_age_increase 160.00 > max 60.00" in result.failed_checks
    assert "dlq_pressure_added 0.7000 > max 0.5000" in result.failed_checks
    assert "replay_pressure_increase 0.3500 > max 0.2000" in result.failed_checks


def test_write_report_persists_profile_tier(tmp_path) -> None:
    result = _evaluate_profile(
        profile_name="steady_state",
        records_submitted=100,
        batches_submitted=2,
        started_at=10.0,
        ended_at=20.0,
        baseline_health={
            "summary": {"backlog_jobs": 0},
            "slo": {"backlog_age_seconds": 0.0},
            "error_budget": {
                "dlq_events_in_window": 0,
                "dlq_budget_events_per_window": 10,
                "replay_backlog_pressure_ratio": "0.0000",
            },
        },
        health={
            "summary": {"backlog_jobs": 0},
            "slo": {"backlog_age_seconds": 0.0},
            "error_budget": {
                "dlq_events_in_window": 0,
                "dlq_budget_events_per_window": 10,
                "replay_backlog_pressure_ratio": "0.0000",
            },
        },
        drain_seconds=None,
        thresholds={
            "min_throughput_rps": 1.0,
            "max_backlog_age_increase_seconds": 60.0,
            "max_dlq_pressure_ratio_added": 0.5,
            "max_replay_pressure_ratio_increase": 0.1,
            "max_drain_seconds": None,
        },
    )

    json_path, md_path = _write_report(
        output_dir=tmp_path,
        run_id="RUN1",
        profile_tier="full",
        results=[result],
        enforce=True,
    )

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = md_path.read_text(encoding="utf-8")

    assert payload["profile_tier"] == "full"
    assert "- Profile tier: full" in markdown
