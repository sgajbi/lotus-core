"""Run repository quality tools only when the active interpreter matches the CI lock."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOCK_FILE = ROOT / "requirements" / "ci-tooling.lock.txt"
EXACT_PIN_PATTERN = re.compile(r"^(?P<name>[A-Za-z0-9_.-]+)==(?P<version>[^\s;]+)$")
MODULE_BY_DISTRIBUTION = {
    "bandit": "bandit",
    "deptry": "deptry",
    "interrogate": "interrogate",
    "mypy": "mypy",
    "pip-audit": "pip_audit",
    "radon": "radon",
    "ruff": "ruff",
    "vulture": "vulture",
    "xenon": "xenon",
}


class ToolingContractError(ValueError):
    """Raised when the quality-tool lock or active interpreter is not governed."""


def canonical_distribution_name(value: str) -> str:
    """Apply the package-name normalization used for lock lookup."""

    return re.sub(r"[-_.]+", "-", value.strip()).lower()


def load_exact_pins(lock_file: Path = DEFAULT_LOCK_FILE) -> dict[str, str]:
    """Load one exact version for every non-comment requirement in the CI tooling lock."""

    pins: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        lock_file.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = EXACT_PIN_PATTERN.fullmatch(line)
        if match is None:
            raise ToolingContractError(
                f"{lock_file}:{line_number} must use one exact NAME==VERSION pin"
            )
        name = canonical_distribution_name(match.group("name"))
        if name in pins:
            raise ToolingContractError(f"{lock_file} contains duplicate pin for {name}")
        pins[name] = match.group("version")
    return pins


def require_pinned_tool(
    distribution: str,
    *,
    lock_file: Path = DEFAULT_LOCK_FILE,
    version_resolver: Callable[[str], str] | None = None,
) -> str:
    """Return the exact pin after proving the active interpreter has that version."""

    name = canonical_distribution_name(distribution)
    expected = load_exact_pins(lock_file).get(name)
    if expected is None:
        raise ToolingContractError(f"{name} has no exact pin in {lock_file}")
    resolve_version = version_resolver or version
    try:
        actual = resolve_version(name)
    except PackageNotFoundError as error:
        raise ToolingContractError(
            _mismatch_message(
                name=name, expected=expected, actual="not installed", lock_file=lock_file
            )
        ) from error
    if actual != expected:
        raise ToolingContractError(
            _mismatch_message(name=name, expected=expected, actual=actual, lock_file=lock_file)
        )
    return expected


def build_module_command(
    distribution: str,
    arguments: Sequence[str],
    *,
    python_executable: str = sys.executable,
) -> list[str]:
    """Build an OS-neutral argv list without shell quoting or command-window indirection."""

    name = canonical_distribution_name(distribution)
    try:
        module = MODULE_BY_DISTRIBUTION[name]
    except KeyError as error:
        raise ToolingContractError(f"{name} has no governed Python module entrypoint") from error
    return [python_executable, "-m", module, *arguments]


def run_pinned_tool(
    distribution: str,
    arguments: Sequence[str],
    *,
    lock_file: Path = DEFAULT_LOCK_FILE,
) -> int:
    """Verify and run one quality tool in the same active interpreter."""

    require_pinned_tool(distribution, lock_file=lock_file)
    command = build_module_command(distribution, arguments)
    return subprocess.run(command, cwd=ROOT, check=False).returncode


def _mismatch_message(*, name: str, expected: str, actual: str, lock_file: Path) -> str:
    return (
        f"governed quality-tool mismatch: {name} expected {expected} from {lock_file}, "
        f"active interpreter has {actual}. Run `make install` from the repository root, then "
        "rerun the repository-native target through the worktree-fenced Make entry point."
    )


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lock-file",
        type=Path,
        default=DEFAULT_LOCK_FILE,
        help="Exact CI tooling requirements lock.",
    )
    subparsers = parser.add_subparsers(dest="action", required=True)
    verify_parser = subparsers.add_parser("verify", help="Verify one or more installed tools.")
    verify_parser.add_argument("tools", nargs="+")
    run_parser = subparsers.add_parser("run", help="Verify and run a module-backed tool.")
    run_parser.add_argument("tool")
    run_parser.add_argument("arguments", nargs=argparse.REMAINDER)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(tuple(argv or sys.argv[1:]))
    try:
        if args.action == "verify":
            for tool in args.tools:
                expected = require_pinned_tool(tool, lock_file=args.lock_file)
                print(f"Governed quality tool verified: {tool}=={expected}")
            return 0
        return run_pinned_tool(args.tool, args.arguments, lock_file=args.lock_file)
    except (OSError, ToolingContractError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
