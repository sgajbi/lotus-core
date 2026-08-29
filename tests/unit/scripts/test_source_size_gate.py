from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path

import pytest

from scripts.quality import source_size_gate as gate


def _valid_policy_payload() -> dict[str, object]:
    return {
        "schema_version": "lotus.core.module-size-baseline.v1",
        "recorded_on": "2026-08-29",
        "tracked_files_only": True,
        "threshold_lines": 3,
        "scan_roots": ["src"],
        "entries": [
            {
                "path": "src/legacy.py",
                "lines": 4,
                "owner": "owner",
                "rationale": "legacy debt",
                "issue": "#1",
                "expires_on": "2099-01-01",
            }
        ],
    }


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


def test_gate_rejects_unobserved_baseline_module() -> None:
    assert gate.source_size_violations(
        {"src/small.py": 1},
        policy=_policy(),
        today=date(2026, 8, 29),
    ) == ["src/legacy.py: baseline module was not observed; remove stale baseline"]


def test_load_policy_rejects_path_traversal(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "schema_version": "lotus.core.module-size-baseline.v1",
                "recorded_on": "2026-08-29",
                "tracked_files_only": True,
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


def test_tracked_line_counts_exclude_untracked_files(tmp_path: Path) -> None:
    source_root = tmp_path / "src"
    source_root.mkdir()
    (source_root / "tracked.py").write_text("one = 1\ntwo = 2\n", encoding="utf-8")
    (source_root / "untracked.py").write_text("one = 1\ntwo = 2\nthree = 3\n", encoding="utf-8")
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "src/tracked.py"], cwd=tmp_path, check=True)

    assert gate.tracked_python_line_counts(tmp_path, ("src",)) == {"src/tracked.py": 2}


def test_tracked_line_counts_fail_when_indexed_file_is_missing(tmp_path: Path) -> None:
    source_root = tmp_path / "src"
    source_root.mkdir()
    source = source_root / "missing.py"
    source.write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "src/missing.py"], cwd=tmp_path, check=True)
    source.unlink()

    with pytest.raises(ValueError, match="missing from the checkout"):
        gate.tracked_python_line_counts(tmp_path, ("src",))


def test_tracked_line_counts_fail_closed_for_empty_inventory(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)

    with pytest.raises(ValueError, match="No tracked Python files"):
        gate.tracked_python_line_counts(tmp_path, ("src",))


def test_tracked_line_counts_surface_git_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    completed = subprocess.CompletedProcess(["git"], 1, stdout="", stderr="inventory failed")
    monkeypatch.setattr(gate.subprocess, "run", lambda *args, **kwargs: completed)

    with pytest.raises(RuntimeError, match="inventory failed"):
        gate.tracked_python_line_counts(tmp_path, ("src",))


def test_main_fails_for_real_new_oversized_tracked_module(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source_root = tmp_path / "src"
    source_root.mkdir()
    (source_root / "new.py").write_text("one = 1\ntwo = 2\nthree = 3\nfour = 4\n", encoding="utf-8")
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "src/new.py"], cwd=tmp_path, check=True)
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "schema_version": "lotus.core.module-size-baseline.v1",
                "recorded_on": "2026-08-29",
                "tracked_files_only": True,
                "threshold_lines": 3,
                "scan_roots": ["src"],
                "entries": [],
            }
        ),
        encoding="utf-8",
    )

    assert gate.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)]) == 1
    assert "src/new.py: 4 lines exceeds 3" in capsys.readouterr().out


def test_load_policy_rejects_non_string_scan_root(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "schema_version": "lotus.core.module-size-baseline.v1",
                "recorded_on": "2026-08-29",
                "tracked_files_only": True,
                "threshold_lines": 3,
                "scan_roots": [1],
                "entries": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must be non-empty strings"):
        gate.load_policy(baseline)


def test_load_policy_accepts_reviewed_entry(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(_valid_policy_payload()), encoding="utf-8")

    policy = gate.load_policy(path)

    assert policy.threshold_lines == 3
    assert policy.scan_roots == ("src",)
    assert policy.baseline_lines == {"src/legacy.py": 4}
    assert policy.expires_on == {"src/legacy.py": date(2099, 1, 1)}


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("schema", "unsupported schema_version"),
        ("tracked", "tracked_files_only"),
        ("date", "recorded_on must be an ISO date"),
        ("threshold", "threshold_lines must be a positive integer"),
        ("roots", "scan_roots must be a non-empty list"),
        ("duplicate_root", "must not contain duplicates"),
        ("root_traversal", "scan_roots must be repository-relative"),
        ("entries", "entries must be a list"),
        ("entry", "entry 0 must be an object"),
        ("path", "must name a path"),
        ("duplicate", "Duplicate module-size baseline path"),
        ("lines", "must exceed threshold 3"),
        ("owner", "must define owner"),
        ("expiry", "invalid expires_on"),
    ],
)
def test_load_policy_rejects_malformed_contract(tmp_path: Path, case: str, message: str) -> None:
    payload = _valid_policy_payload()
    roots = payload["scan_roots"]
    entries = payload["entries"]
    assert isinstance(roots, list)
    assert isinstance(entries, list)
    entry = entries[0]
    assert isinstance(entry, dict)
    if case == "schema":
        payload["schema_version"] = "unsupported"
    elif case == "tracked":
        payload["tracked_files_only"] = False
    elif case == "date":
        payload["recorded_on"] = "invalid"
    elif case == "threshold":
        payload["threshold_lines"] = 0
    elif case == "roots":
        payload["scan_roots"] = []
    elif case == "duplicate_root":
        roots.append("src")
    elif case == "root_traversal":
        roots[0] = "../src"
    elif case == "entries":
        payload["entries"] = None
    elif case == "entry":
        entries[0] = None
    elif case == "path":
        entry["path"] = ""
    elif case == "duplicate":
        entries.append(dict(entry))
    elif case == "lines":
        entry["lines"] = 3
    elif case == "owner":
        entry["owner"] = ""
    elif case == "expiry":
        entry["expires_on"] = "invalid"
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        gate.load_policy(path)


def test_main_passes_real_tracked_module_below_budget(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source_root = tmp_path / "src"
    source_root.mkdir()
    (source_root / "small.py").write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "src/small.py"], cwd=tmp_path, check=True)
    payload = _valid_policy_payload()
    payload["entries"] = []
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps(payload), encoding="utf-8")

    assert gate.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)]) == 0
    assert "1 tracked modules, threshold=3, baseline=0" in capsys.readouterr().out
