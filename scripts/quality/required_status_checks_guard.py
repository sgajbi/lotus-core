from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from scripts.quality.required_status_checks import (
    DEFAULT_MANIFEST_PATH,
    RequiredStatusChecksError,
    desired_protection_payload,
    load_live_protection,
    load_manifest,
    validate_live_protection,
    validate_manifest_against_workflows,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate governed required status checks")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--verify-live", action="store_true")
    parser.add_argument("--print-desired-protection", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        validate_manifest_against_workflows(manifest, repository_root=args.repository_root)
        if args.print_desired_protection:
            print(json.dumps(desired_protection_payload(manifest), sort_keys=True))
            return 0
        if args.verify_live:
            protection = load_live_protection(
                repository=manifest.repository,
                branch=manifest.branch,
            )
            validate_live_protection(manifest, protection)
    except RequiredStatusChecksError as exc:
        print(f"required status checks guard failed: {exc}")
        return 1
    print(
        "required status checks guard passed: "
        f"checks={len(manifest.required_checks)} live={args.verify_live}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
