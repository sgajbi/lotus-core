from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.quality import maintainability_gate as gate


def test_default_gate_rejects_c_and_names_the_module_and_rank() -> None:
    report = {"src/bad.py": {"mi": 4.25, "rank": "C"}}

    assert gate.maintainability_violations(report) == [
        "src/bad.py: maintainability rank C (4.25) exceeds B without a reviewed baseline"
    ]


def test_default_gate_accepts_a_and_b_modules() -> None:
    report = {
        "src/a.py": {"mi": 100.0, "rank": "A"},
        "src/b.py": {"mi": 15.0, "rank": "B"},
    }

    assert gate.maintainability_violations(report) == []


def test_gate_accepts_exact_reviewed_debt() -> None:
    report = {r"src\legacy.py": {"mi": 4.25, "rank": "C"}}

    assert (
        gate.maintainability_violations(
            report,
            baseline={"src/legacy.py": ("C", 4.25)},
        )
        == []
    )


@pytest.mark.parametrize(("mi", "word"), [(3.25, "worsened"), (5.25, "improved")])
def test_gate_rejects_changed_baseline_and_requires_ratchet(mi: float, word: str) -> None:
    report = {"src/legacy.py": {"mi": mi, "rank": "C"}}

    violations = gate.maintainability_violations(
        report,
        baseline={"src/legacy.py": ("C", 4.25)},
    )

    assert len(violations) == 1
    assert word in violations[0]
    assert "ratchet the baseline" in violations[0]


def test_gate_rejects_stale_baseline_after_rank_improves() -> None:
    report = {"src/legacy.py": {"mi": 10.0, "rank": "B"}}

    assert gate.maintainability_violations(
        report,
        baseline={"src/legacy.py": ("C", 4.25)},
    ) == ["src/legacy.py: improved to rank B (10.00); remove stale baseline C (4.25)"]


def test_gate_fails_closed_for_empty_report() -> None:
    assert gate.maintainability_violations({}) == [
        "no tracked Python modules were analyzed; refusing to pass an empty scan"
    ]


def test_load_baseline_requires_owner_rationale_and_issue(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "lotus.core.maintainability-baseline.v1",
                "max_allowed_rank": "B",
                "entries": [{"path": "src/legacy.py", "rank": "C", "mi": 4.25}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must define owner"):
        gate.load_baseline(path, max_allowed_rank="B")
