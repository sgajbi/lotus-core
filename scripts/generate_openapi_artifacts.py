"""Generate deterministic OpenAPI artifacts for portable lint tools."""

from __future__ import annotations

import sys
from argparse import ArgumentParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_OPENAPI_OUTPUT_DIR = REPO_ROOT / "output" / "openapi"


def main() -> int:
    from scripts.openapi_quality_gate import write_openapi_artifacts

    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OPENAPI_OUTPUT_DIR,
        help="Directory where per-service OpenAPI JSON artifacts are written.",
    )
    args = parser.parse_args()

    generated_paths = write_openapi_artifacts(output_dir=args.output_dir)
    for path in generated_paths:
        print(f"Wrote OpenAPI artifact: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
