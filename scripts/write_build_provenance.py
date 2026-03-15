"""Write a lightweight build provenance manifest for a service image."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
    ).strip()


def _extract_base_image(dockerfile: Path) -> str:
    for line in dockerfile.read_text(encoding="utf-8").splitlines():
        if line.startswith("ARG PYTHON_IMAGE="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"Missing ARG PYTHON_IMAGE in {dockerfile}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dockerfile", required=True)
    parser.add_argument("--image-tag", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dockerfile = (REPO_ROOT / args.dockerfile).resolve()
    runtime_lock = REPO_ROOT / "requirements" / "shared-runtime.lock.txt"
    payload = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "git_head": _git_head(),
        "image_tag": args.image_tag,
        "dockerfile": str(dockerfile.relative_to(REPO_ROOT)),
        "dockerfile_sha256": _sha256(dockerfile),
        "base_image": _extract_base_image(dockerfile),
        "runtime_lock": str(runtime_lock.relative_to(REPO_ROOT)),
        "runtime_lock_sha256": _sha256(runtime_lock),
    }
    output_path = (REPO_ROOT / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
