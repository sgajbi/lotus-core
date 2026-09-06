from pathlib import Path

import pytest

from scripts.quality import documentation_text_integrity_guard as guard


def test_accepts_printable_text_and_line_endings(tmp_path: Path) -> None:
    path = tmp_path / "valid.md"
    path.write_bytes(b"# Valid\r\ntext\n")

    assert guard.find_forbidden_control_bytes((path,), repo_root=tmp_path) == []


def test_reports_every_forbidden_control_byte_with_path_and_offset(tmp_path: Path) -> None:
    path = tmp_path / "docs" / "corrupt.md"
    path.parent.mkdir()
    path.write_bytes(b"a\x08b\x09c\x0cd\x1be\x00f\rg\x7f")

    assert guard.find_forbidden_control_bytes((path,), repo_root=tmp_path) == [
        "docs/corrupt.md: offset 1: 0x08",
        "docs/corrupt.md: offset 3: 0x09",
        "docs/corrupt.md: offset 5: 0x0c",
        "docs/corrupt.md: offset 7: 0x1b",
        "docs/corrupt.md: offset 9: 0x00",
        "docs/corrupt.md: offset 11: 0x0d",
        "docs/corrupt.md: offset 13: 0x7f",
    ]


def test_discovers_only_git_tracked_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subprocess_commands: list[tuple[list[str], dict[str, object]]] = []

    class Completed:
        stdout = b"README.md\0docs/guide.md\0"

    def run(args: list[str], **kwargs: object) -> Completed:
        subprocess_commands.append((args, kwargs))
        return Completed()

    monkeypatch.setattr(guard.subprocess, "run", run)
    paths = guard.tracked_markdown_paths(repo_root=tmp_path)

    assert paths == (tmp_path / "README.md", tmp_path / "docs" / "guide.md")
    assert subprocess_commands[0][0] == ["git", "ls-files", "-z", "--", "*.md"]
    assert subprocess_commands[0][1]["cwd"] == tmp_path
