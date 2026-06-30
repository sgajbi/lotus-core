"""Run Spectral against deterministic lotus-core OpenAPI artifacts."""

from __future__ import annotations

import subprocess
import sys
from argparse import ArgumentParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_OPENAPI_OUTPUT_DIR = REPO_ROOT / "output" / "openapi"
DEFAULT_RULESET = REPO_ROOT / ".spectral.yaml"


def npx_executable(platform: str = sys.platform) -> str:
    if platform.startswith("win"):
        return "npx.cmd"
    return "npx"


def spectral_command(
    artifacts: list[Path],
    *,
    ruleset: Path = DEFAULT_RULESET,
    fail_severity: str = "warn",
    platform: str = sys.platform,
) -> list[str]:
    return [
        npx_executable(platform),
        "--yes",
        "@stoplight/spectral-cli",
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
    from scripts.openapi_quality_gate import write_openapi_artifacts

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
