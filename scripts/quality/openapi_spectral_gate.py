"""Run Spectral against deterministic lotus-core OpenAPI artifacts."""

from __future__ import annotations

import subprocess
import sys
from argparse import ArgumentParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_OPENAPI_OUTPUT_DIR = REPO_ROOT / "output" / "openapi"
DEFAULT_RULESET = REPO_ROOT / ".spectral.yaml"
SPECTRAL_TOOL_ROOT = REPO_ROOT / "tools" / "api_governance"


def npm_executable(platform: str = sys.platform) -> str:
    """Return the npm executable name for the current platform."""

    return "npm.cmd" if platform.startswith("win") else "npm"


def npm_ci_command(platform: str = sys.platform) -> list[str]:
    """Return the deterministic dependency-install command."""

    return [
        npm_executable(platform),
        "ci",
        "--ignore-scripts",
        "--no-audit",
        "--no-fund",
    ]


def install_spectral_tooling(*, platform: str = sys.platform) -> int:
    """Install the lock-backed API-governance tooling in its owned directory."""

    completed = subprocess.run(
        npm_ci_command(platform),
        cwd=SPECTRAL_TOOL_ROOT,
        check=False,
    )
    return completed.returncode


def spectral_executable(
    platform: str = sys.platform,
    *,
    tool_root: Path = SPECTRAL_TOOL_ROOT,
) -> str:
    """Return the lock-installed Spectral executable for the current platform."""

    executable = "spectral.cmd" if platform.startswith("win") else "spectral"
    return str(tool_root / "node_modules" / ".bin" / executable)


def spectral_command(
    artifacts: list[Path],
    *,
    ruleset: Path = DEFAULT_RULESET,
    fail_severity: str = "warn",
    platform: str = sys.platform,
    tool_root: Path = SPECTRAL_TOOL_ROOT,
) -> list[str]:
    return [
        spectral_executable(platform, tool_root=tool_root),
        "lint",
        *[str(path) for path in artifacts],
        "--ruleset",
        str(ruleset),
        "--fail-severity",
        fail_severity,
    ]


def run_spectral_lint(
    artifacts: list[Path],
    *,
    ruleset: Path = DEFAULT_RULESET,
    fail_severity: str = "warn",
) -> int:
    if not artifacts:
        print("No OpenAPI artifacts were generated.")
        return 1
    command = spectral_command(artifacts, ruleset=ruleset, fail_severity=fail_severity)
    completed = subprocess.run(command, cwd=REPO_ROOT, check=False)
    return completed.returncode


def main() -> int:
    from scripts.quality.openapi_quality_gate import write_openapi_artifacts

    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OPENAPI_OUTPUT_DIR,
        help="Directory where per-service OpenAPI JSON artifacts are written.",
    )
    parser.add_argument(
        "--ruleset",
        type=Path,
        default=DEFAULT_RULESET,
        help="Spectral ruleset used for enforced portable OpenAPI linting.",
    )
    parser.add_argument(
        "--fail-severity",
        default="warn",
        choices=("error", "warn", "info", "hint"),
        help="Lowest Spectral severity that fails the gate.",
    )
    args = parser.parse_args()

    install_returncode = install_spectral_tooling()
    if install_returncode != 0:
        print(
            "Failed to install lock-backed API-governance tooling.",
            file=sys.stderr,
        )
        return install_returncode

    artifacts = write_openapi_artifacts(output_dir=args.output_dir)
    for path in artifacts:
        print(f"Wrote OpenAPI artifact: {path}", flush=True)
    return run_spectral_lint(
        artifacts,
        ruleset=args.ruleset,
        fail_severity=args.fail_severity,
    )


if __name__ == "__main__":
    raise SystemExit(main())
