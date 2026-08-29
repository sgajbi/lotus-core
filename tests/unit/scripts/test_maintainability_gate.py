from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.quality import maintainability_gate as gate


def _valid_baseline_payload() -> dict[str, object]:
    return {
        "schema_version": "lotus.core.maintainability-baseline.v1",
        "max_allowed_rank": "B",
        "recorded_on": "2026-08-29",
        "tracked_files_only": True,
        "entries": [
            {
                "path": "src/legacy.py",
                "rank": "C",
                "mi": 4.25,
                "owner": "owner",
                "rationale": "legacy debt",
                "issue": "#1",
            }
        ],
    }


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


def test_gate_rejects_non_numeric_maintainability_index() -> None:
    assert gate.maintainability_violations({"src/bad.py": {"mi": None, "rank": "C"}}) == [
        "src/bad.py: maintainability index is missing or non-numeric"
    ]


def test_gate_rejects_unknown_rank() -> None:
    assert gate.maintainability_violations({"src/bad.py": {"mi": 1.0, "rank": "UNKNOWN"}}) == [
        "src/bad.py: unknown maintainability rank UNKNOWN (1.00)"
    ]


def test_gate_rejects_unobserved_baseline_module() -> None:
    assert gate.maintainability_violations(
        {"src/good.py": {"mi": 100.0, "rank": "A"}},
        baseline={"src/missing.py": ("C", 4.25)},
    ) == ["src/missing.py: baseline C (4.25) was not observed; remove stale baseline"]


@pytest.mark.parametrize("root", ["", "--help", "../src"])
def test_scan_roots_reject_empty_options_and_traversal(root: str) -> None:
    with pytest.raises(ValueError, match="must be repository-relative"):
        gate._validated_roots([root])


def test_scan_roots_reject_absolute_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be repository-relative"):
        gate._validated_roots([str(tmp_path)])


def test_scan_roots_reject_empty_collection() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        gate._validated_roots([])


def test_radon_scan_uses_only_git_tracked_python_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "src"
    source_root.mkdir()
    (source_root / "tracked.py").write_text("value = 1\n", encoding="utf-8")
    (source_root / "untracked.py").write_text("other = 2\n", encoding="utf-8")
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "src/tracked.py"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)

    report = gate.run_radon_maintainability(["src"])

    assert set(report) == {"src/tracked.py"}
    assert report["src/tracked.py"]["rank"] == "A"


def test_tracked_python_inventory_fails_closed_when_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "src").mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="No tracked Python files"):
        gate.tracked_python_paths(["src"])


def test_tracked_python_inventory_surfaces_git_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed = subprocess.CompletedProcess(["git"], 1, stdout="", stderr="inventory failed")
    monkeypatch.setattr(gate.subprocess, "run", lambda *args, **kwargs: completed)

    with pytest.raises(RuntimeError, match="inventory failed"):
        gate.tracked_python_paths(["src"])


def test_radon_scan_surfaces_tool_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    completed = subprocess.CompletedProcess(["radon"], 2, stdout="", stderr="radon failed")
    monkeypatch.setattr(gate.subprocess, "run", lambda *args, **kwargs: completed)

    with pytest.raises(RuntimeError, match="radon failed"):
        gate.run_radon_maintainability(["src"])


def test_load_baseline_accepts_reviewed_entry(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(_valid_baseline_payload()), encoding="utf-8")

    assert gate.load_baseline(path, max_allowed_rank="B") == {"src/legacy.py": ("C", 4.25)}


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("schema", "unsupported schema_version"),
        ("ceiling", "does not match the active gate"),
        ("tracked", "tracked_files_only"),
        ("date", "recorded_on must be an ISO date"),
        ("entries", "entries must be a list"),
        ("entry", "entry 0 must be an object"),
        ("path", "must name a path"),
        ("traversal", "must be repository-relative"),
        ("duplicate", "Duplicate maintainability baseline path"),
        ("rank", "must exceed B"),
        ("mi", "must define numeric mi"),
        ("owner", "must define owner"),
    ],
)
def test_load_baseline_rejects_malformed_policy(tmp_path: Path, case: str, message: str) -> None:
    payload = _valid_baseline_payload()
    entries = payload["entries"]
    assert isinstance(entries, list)
    entry = entries[0]
    assert isinstance(entry, dict)
    if case == "schema":
        payload["schema_version"] = "unsupported"
    elif case == "ceiling":
        payload["max_allowed_rank"] = "A"
    elif case == "tracked":
        payload["tracked_files_only"] = False
    elif case == "date":
        payload["recorded_on"] = "invalid"
    elif case == "entries":
        payload["entries"] = None
    elif case == "entry":
        entries[0] = None
    elif case == "path":
        entry["path"] = ""
    elif case == "traversal":
        entry["path"] = "../legacy.py"
    elif case == "duplicate":
        entries.append(dict(entry))
    elif case == "rank":
        entry["rank"] = "B"
    elif case == "mi":
        entry["mi"] = "low"
    elif case == "owner":
        entry["owner"] = ""
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        gate.load_baseline(path, max_allowed_rank="B")


def test_main_fails_closed_for_invalid_baseline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text("{}", encoding="utf-8")

    assert gate.main(["src", "--baseline", str(baseline)]) == 1
    assert "unsupported schema_version" in capsys.readouterr().err


def test_main_passes_clean_report(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        gate,
        "run_radon_maintainability",
        lambda roots: {"src/good.py": {"mi": 100.0, "rank": "A"}},
    )

    assert gate.main(["src"]) == 0
    assert "1 tracked modules, ceiling=B, baseline=0" in capsys.readouterr().out


def test_main_returns_failure_for_policy_violation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        gate,
        "run_radon_maintainability",
        lambda roots: {"src/bad.py": {"mi": 4.25, "rank": "C"}},
    )

    assert gate.main(["src"]) == 1
    assert "src/bad.py: maintainability rank C" in capsys.readouterr().out
