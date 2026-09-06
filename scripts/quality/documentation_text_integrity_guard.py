from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_LINE_FEED = 0x0A
_CARRIAGE_RETURN = 0x0D


def tracked_markdown_paths(*, repo_root: Path = REPO_ROOT) -> tuple[Path, ...]:
    completed = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.md"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    return tuple(
        repo_root / Path(raw_path.decode("utf-8"))
        for raw_path in completed.stdout.split(b"\0")
        if raw_path
    )


def find_forbidden_control_bytes(
    paths: tuple[Path, ...],
    *,
    repo_root: Path = REPO_ROOT,
) -> list[str]:
    violations: list[str] = []
    for path in paths:
        content = path.read_bytes()
        for offset, value in enumerate(content):
            is_line_feed = value == _LINE_FEED
            is_crlf_carriage_return = (
                value == _CARRIAGE_RETURN
                and offset + 1 < len(content)
                and content[offset + 1] == _LINE_FEED
            )
            if value < 0x20 and not (is_line_feed or is_crlf_carriage_return):
                relative_path = path.relative_to(repo_root).as_posix()
                violations.append(f"{relative_path}: offset {offset}: 0x{value:02x}")
    return violations


def main() -> int:
    try:
        paths = tracked_markdown_paths()
    except subprocess.CalledProcessError as error:
        print(f"Documentation text integrity failed: git ls-files exited {error.returncode}.")
        return 1

    violations = find_forbidden_control_bytes(paths)
    if violations:
        print("Documentation text integrity failed:")
        for violation in violations:
            print(f"- {violation}")
        return 1

    print(f"Documentation text integrity passed: {len(paths)} tracked Markdown files checked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
