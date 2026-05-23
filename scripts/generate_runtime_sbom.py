from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

try:
    from scripts.dependency_health_check import (
        ROOT,
        RUNTIME_LOCK_FILE,
        pip_audit_ignore_options,
    )
except ModuleNotFoundError:
    from dependency_health_check import (  # type: ignore[no-redef]
        ROOT,
        RUNTIME_LOCK_FILE,
        pip_audit_ignore_options,
    )


DEFAULT_OUTPUT_FILE = ROOT / "output" / "build-evidence" / "shared-runtime-sbom.cdx.json"


def runtime_sbom_command(
    python_bin: Path,
    *,
    requirements_file: Path,
    output_file: Path,
) -> list[str]:
    return [
        str(python_bin),
        "-m",
        "pip_audit",
        "-r",
        str(requirements_file),
        "--format",
        "cyclonedx-json",
        "-o",
        str(output_file),
        *pip_audit_ignore_options(),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a CycloneDX SBOM for the shared runtime lock file."
    )
    parser.add_argument(
        "--requirements",
        type=Path,
        default=RUNTIME_LOCK_FILE,
        help="Runtime requirements lock file to audit.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_FILE,
        help="CycloneDX JSON SBOM output path.",
    )
    args = parser.parse_args()

    output_file = args.output.resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        runtime_sbom_command(
            Path(sys.executable),
            requirements_file=args.requirements.resolve(),
            output_file=output_file,
        ),
        cwd=ROOT,
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
