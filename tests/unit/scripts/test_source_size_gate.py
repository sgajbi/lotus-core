from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from scripts.quality import source_size_gate as gate


def _policy(*, baseline_lines: int = 4) -> gate.SourceSizePolicy:
    return gate.SourceSizePolicy(
        threshold_lines=3,
        scan_roots=("src",),
        baseline_lines={"src/legacy.py": baseline_lines},
        expires_on={"src/legacy.py": date(2099, 1, 1)},
    )


def test_gate_accepts_exact_zero_headroom_baseline() -> None:
    assert (
        gate.source_size_violations(
            {"src/legacy.py": 4, "src/small.py": 3},
            policy=_policy(),
            today=date(2026, 8, 29),
        )
        == []
    )


def test_gate_rejects_new_oversized_module_with_actionable_path_and_limit() -> None:
    violations = gate.source_size_violations(
        {"src/legacy.py": 4, "src/new.py": 5},
        policy=_policy(),
        today=date(2026, 8, 29),
    )

    assert violations == ["src/new.py: 5 lines exceeds 3 without a reviewed baseline"]


@pytest.mark.parametrize(
    ("lines", "message"),
    [
        (5, "grew to 5 lines from zero-headroom baseline 4"),
        (3, "now has 3 lines at or below 3; remove the resolved baseline"),
    ],
)
def test_gate_rejects_growth_or_unbanked_improvement(lines: int, message: str) -> None:
    violations = gate.source_size_violations(
        {"src/legacy.py": lines},
        policy=_policy(),
        today=date(2026, 8, 29),
    )

    assert violations == [f"src/legacy.py: {message}"]


def test_gate_rejects_shrink_that_remains_above_threshold() -> None:
    assert gate.source_size_violations(
        {"src/legacy.py": 4},
        policy=_policy(baseline_lines=5),
        today=date(2026, 8, 29),
    ) == ["src/legacy.py: shrank to 4 lines from baseline 5; ratchet the baseline"]


def test_gate_fails_closed_for_empty_scan() -> None:
    assert gate.source_size_violations({}, policy=_policy()) == [
        "no tracked Python modules were measured; refusing to pass an empty scan"
    ]


def test_gate_rejects_expired_baseline() -> None:
    policy = gate.SourceSizePolicy(
        threshold_lines=3,
        scan_roots=("src",),
        baseline_lines={"src/legacy.py": 4},
        expires_on={"src/legacy.py": date(2026, 8, 28)},
    )

    assert gate.source_size_violations(
        {"src/legacy.py": 4},
        policy=policy,
        today=date(2026, 8, 29),
    ) == ["src/legacy.py: module-size baseline expired on 2026-08-28"]


def test_load_policy_rejects_path_traversal(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "schema_version": "lotus.core.module-size-baseline.v1",
                "threshold_lines": 3,
                "scan_roots": ["src"],
                "entries": [
                    {
                        "path": "../legacy.py",
                        "lines": 4,
                        "owner": "owner",
                        "rationale": "legacy",
                        "issue": "#1",
                        "expires_on": "2099-01-01",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must be repository-relative"):
        gate.load_policy(baseline_path)
