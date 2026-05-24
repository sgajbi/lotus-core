from pathlib import Path

WORKFLOW_PATH = Path(".github/workflows/main-releasability.yml")


def test_institutional_completion_gate_is_manual_opt_in() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "run_institutional_completion:" in workflow
    assert (
        'description: "Run the approval-grade 1000-portfolio institutional completion '
        'and sign-off jobs."'
    ) in workflow
    assert "default: false" in workflow
    assert "type: boolean" in workflow
    assert (
        "if: ${{ github.event_name == 'workflow_dispatch' "
        "&& inputs.run_institutional_completion }}"
    ) in workflow


def test_institutional_completion_is_not_default_schedule_or_push_truth() -> None:
    runbook = Path("docs/operations/Institutional-Signoff-Runbook.md").read_text(
        encoding="utf-8"
    )

    assert "run_institutional_completion=true" in runbook
    assert "Routine `main` push, scheduled, and default manual runs intentionally skip" in runbook
    assert "1000-portfolio institutional completion" in runbook
