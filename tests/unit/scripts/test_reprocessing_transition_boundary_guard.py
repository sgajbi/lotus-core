from pathlib import Path

from scripts.quality.reprocessing_transition_boundary_guard import (
    find_reprocessing_transition_boundary_findings,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_owned_callers(root: Path) -> None:
    for name in ("reprocessing_worker.py", "fx_revaluation_job_processor.py"):
        _write(
            root / "src/services/valuation_orchestrator_service/app/core" / name,
            "async def transition(repository):\n"
            "    await repository.requeue_owned_effective_dated_job(1, lease_token='a')\n",
        )


def test_guard_accepts_repository_owned_effective_dated_requeue(tmp_path: Path) -> None:
    _write_owned_callers(tmp_path)

    assert find_reprocessing_transition_boundary_findings(tmp_path) == []


def test_guard_rejects_positional_direct_pending_transition(tmp_path: Path) -> None:
    _write_owned_callers(tmp_path)
    path = tmp_path / "src/services/example.py"
    _write(
        path,
        "async def transition(repository):\n"
        "    await repository.update_job_status(1, 'PENDING', lease_token='a')\n",
    )

    findings = find_reprocessing_transition_boundary_findings(tmp_path)

    assert [(finding.path, finding.line) for finding in findings] == [
        ("src/services/example.py", 2)
    ]


def test_guard_rejects_keyword_direct_pending_transition(tmp_path: Path) -> None:
    _write_owned_callers(tmp_path)
    path = tmp_path / "src/services/example.py"
    _write(
        path,
        "async def transition(repository):\n"
        "    await repository.update_job_status(1, status='PENDING', lease_token='a')\n",
    )

    findings = find_reprocessing_transition_boundary_findings(tmp_path)

    assert [(finding.path, finding.line) for finding in findings] == [
        ("src/services/example.py", 2)
    ]


def test_guard_requires_both_owned_requeue_callers(tmp_path: Path) -> None:
    _write(
        tmp_path / "src/services/valuation_orchestrator_service/app/core/reprocessing_worker.py",
        "requeue_owned_effective_dated_job()\n",
    )

    findings = find_reprocessing_transition_boundary_findings(tmp_path)

    assert [finding.path for finding in findings] == [
        "src/services/valuation_orchestrator_service/app/core/fx_revaluation_job_processor.py"
    ]
