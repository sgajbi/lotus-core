"""Fail when alias-based API contract patterns are present in lotus-core source."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

PATTERNS = {
    "field_or_param_alias": re.compile(r'\balias\s*=\s*"'),
    "model_dump_by_alias": re.compile(r"\bmodel_dump\(\s*by_alias\s*=\s*True"),
    "response_model_by_alias": re.compile(r"\bresponse_model_by_alias\s*=\s*True"),
    "populate_by_name": re.compile(r"\bpopulate_by_name\b"),
    "legacy_client_term": re.compile(r"\bcif_id\b"),
    "legacy_booking_center_term": re.compile(r"\bbooking_center\b"),
}

# Exempt this script and generated artifacts if any are introduced later.
EXEMPT_PATH_PARTS: tuple[str, ...] = ("/build/", "/dist/")


def _is_exempt(path: Path) -> bool:
    normalized = str(path).replace("\\", "/")
    return any(part in normalized for part in EXEMPT_PATH_PARTS)


def main() -> int:
    findings: list[str] = []
    for file_path in SRC_ROOT.rglob("*.py"):
        if _is_exempt(file_path):
            continue
        content = file_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        for idx, line in enumerate(lines, start=1):
            for rule_name, pattern in PATTERNS.items():
                if pattern.search(line):
                    rel = file_path.relative_to(REPO_ROOT)
                    findings.append(f"{rel}:{idx}: {rule_name}: {line.strip()}")

    if findings:
        print("No-alias contract guard failed. Remove alias-based API patterns:")
        for finding in findings:
            print(f" - {finding}")
        return 1

    print("No-alias contract guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
