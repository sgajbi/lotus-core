"""Tests for Git changed-source parsing and normalization."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.quality.coverage_evidence.changed_source_evidence import (
    ChangedSourceFile,
    SourceChangeType,
    coverage_import_target,
    explicit_changed_sources,
    normalize_repo_path,
    parse_git_name_status,
    read_git_changed_sources,
)


def test_parse_git_name_status_preserves_current_and_previous_paths() -> None:
    output = (
        "A\0src/app/added.py\0"
        "M\0src/app/with spaces.py\0"
        "D\0src/app/deleted.py\0"
        "R087\0src/app/old.py\0src/app/new.py\0"
        "C100\0src/app/source.py\0src/app/copy.py\0"
        "T\0src/app/type_changed.py\0"
    )

    changes = parse_git_name_status(output)

    assert changes == [
        ChangedSourceFile("A", SourceChangeType.ADDED, "src/app/added.py"),
        ChangedSourceFile("M", SourceChangeType.MODIFIED, "src/app/with spaces.py"),
        ChangedSourceFile(
            "D",
            SourceChangeType.DELETED,
            None,
            previous_path="src/app/deleted.py",
        ),
        ChangedSourceFile(
            "R087",
            SourceChangeType.RENAMED,
            "src/app/new.py",
            previous_path="src/app/old.py",
            similarity_percent=87,
        ),
        ChangedSourceFile(
            "C100",
            SourceChangeType.COPIED,
            "src/app/copy.py",
            previous_path="src/app/source.py",
            similarity_percent=100,
        ),
        ChangedSourceFile("T", SourceChangeType.TYPE_CHANGED, "src/app/type_changed.py"),
    ]


def test_parse_git_name_status_normalizes_windows_paths() -> None:
    changes = parse_git_name_status("M\0src\\app\\use_case.py\0")

    assert changes[0].current_path == "src/app/use_case.py"


def test_normalize_repo_path_preserves_leading_dot_directory() -> None:
    assert normalize_repo_path("./.github/workflows/ci.yml") == ".github/workflows/ci.yml"


@pytest.mark.parametrize("path", ["../src/app.py", "/src/app.py", "C:\\src\\app.py", ""])
def test_normalize_repo_path_rejects_paths_outside_repository(path: str) -> None:
    with pytest.raises(ValueError, match="repository-relative"):
        normalize_repo_path(path)


@pytest.mark.parametrize("output", ["M\0", "R100\0old.py\0", "\0path.py\0"])
def test_parse_git_name_status_rejects_incomplete_records(output: str) -> None:
    with pytest.raises(ValueError):
        parse_git_name_status(output)


def test_read_git_changed_sources_uses_merge_base_diff_first(monkeypatch) -> None:
    calls: list[list[str]] = []

    def _fake_run(args, **_kwargs):
        calls.append(list(args))
        return SimpleNamespace(returncode=0, stdout="M\0src/app/use_case.py\0", stderr="")

    monkeypatch.setattr(
        "scripts.quality.coverage_evidence.changed_source_evidence.subprocess.run",
        _fake_run,
    )

    changes = read_git_changed_sources(repo_root=Path("."), base_ref="origin/main")

    assert changes[0].current_path == "src/app/use_case.py"
    assert calls[0] == [
        "git",
        "diff",
        "--name-status",
        "-z",
        "--find-renames",
        "--find-copies",
        "origin/main...HEAD",
    ]


def test_read_git_changed_sources_falls_back_when_merge_base_is_missing(monkeypatch) -> None:
    calls: list[list[str]] = []

    def _fake_run(args, **_kwargs):
        calls.append(list(args))
        if len(calls) == 1:
            return SimpleNamespace(returncode=128, stdout="", stderr="missing merge base")
        return SimpleNamespace(returncode=0, stdout="A\0src/app/new.py\0", stderr="")

    monkeypatch.setattr(
        "scripts.quality.coverage_evidence.changed_source_evidence.subprocess.run",
        _fake_run,
    )

    changes = read_git_changed_sources(repo_root=Path("."), base_ref="origin/main")

    assert changes[0].change_type is SourceChangeType.ADDED
    assert calls[1][-2:] == ["origin/main", "HEAD"]


def test_read_git_changed_sources_fails_closed_when_all_diffs_fail(monkeypatch) -> None:
    def _fake_run(args, **_kwargs):
        return SimpleNamespace(returncode=128, stdout="", stderr=f"invalid revision: {args[-1]}")

    monkeypatch.setattr(
        "scripts.quality.coverage_evidence.changed_source_evidence.subprocess.run",
        _fake_run,
    )

    with pytest.raises(RuntimeError, match="Unable to determine changed source evidence"):
        read_git_changed_sources(repo_root=Path("."), base_ref="missing-base")


def test_explicit_changed_sources_distinguishes_current_and_absent_paths(tmp_path: Path) -> None:
    current = tmp_path / "src/app/current.py"
    current.parent.mkdir(parents=True)
    current.write_text("", encoding="utf-8")

    changes = explicit_changed_sources(
        ["src\\app\\current.py", "src/app/deleted.py"],
        repo_root=tmp_path,
    )

    assert changes == [
        ChangedSourceFile("EXPLICIT", SourceChangeType.EXPLICIT, "src/app/current.py"),
        ChangedSourceFile(
            "EXPLICIT",
            SourceChangeType.EXPLICIT,
            None,
            previous_path="src/app/deleted.py",
        ),
    ]


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (
            "src/services/portfolio_transaction_processing_service/app/domain/cost_basis/"
            "calculation/engine_input.py",
            "src.services.portfolio_transaction_processing_service.app.domain.cost_basis."
            "calculation.engine_input",
        ),
        (
            "src/libs/portfolio-common/portfolio_common/domain/currency.py",
            "portfolio_common.domain.currency",
        ),
        (
            "src/services/query_service/app/services/__init__.py",
            "src.services.query_service.app.services",
        ),
    ],
)
def test_coverage_import_target_maps_repository_source_layouts(path: str, expected: str) -> None:
    assert coverage_import_target(path) == expected


@pytest.mark.parametrize(
    "path",
    ["docs/example.py", "src/app/not-python.txt", "src/libs/other-lib/package/module.py"],
)
def test_coverage_import_target_rejects_unsupported_source_layouts(path: str) -> None:
    with pytest.raises(ValueError):
        coverage_import_target(path)
