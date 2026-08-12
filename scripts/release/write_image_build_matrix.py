"""Emit the source-owned image build matrix for GitHub Actions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.release.prebuild_ci_images import SERVICE_BUILDS


def build_matrix() -> dict[str, list[dict[str, str]]]:
    include = []
    for service, (local_tag, dockerfile) in SERVICE_BUILDS.items():
        image_name = local_tag.removeprefix("lotus-core/").removesuffix(":local")
        include.append(
            {"service": service, "image_name": image_name, "dockerfile": dockerfile}
        )
    return {"include": include}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    payload = json.dumps(build_matrix(), separators=(",", ":"))
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write(f"matrix={payload}\n")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
