"""Tests for Git changed-source parsing and normalization."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.quality.coverage_evidence.changed_source_evidence import (
    ChangedSourceFile,
    SourceChangeType,
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
