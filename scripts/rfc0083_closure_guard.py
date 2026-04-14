"""Validate the RFC-0083 implementation closure ledger."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = REPO_ROOT / "docs" / "standards" / "rfc-0083-implementation-ledger.json"
LEDGER_SPEC_VERSION = "1.0.0"
APPLICATION = "lotus-core"
GOVERNING_RFCS = {"RFC-0082", "RFC-0083"}
EXPECTED_SLICES = set(range(12))
VALID_STATUSES = {"completed", "blocked", "superseded"}


def load_ledger(path: Path = LEDGER_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_ledger(payload: dict[str, Any], *, repo_root: Path = REPO_ROOT) -> list[str]:
    errors: list[str] = []
    if payload.get("specVersion") != LEDGER_SPEC_VERSION:
        errors.append(f"ledger specVersion must be {LEDGER_SPEC_VERSION!r}")
    if payload.get("application") != APPLICATION:
        errors.append(f"ledger application must be {APPLICATION!r}")
    if set(payload.get("governingRfcs", [])) != GOVERNING_RFCS:
        errors.append("ledger governingRfcs must contain RFC-0082 and RFC-0083")
    if payload.get("closureStatus") != "target-model-and-guarded-artifact-closure":
        errors.append("ledger closureStatus must describe guarded target-model closure")
    if payload.get("runtimeProductionStatus") != "not-production-closed":
        errors.append("ledger must not claim runtime production closure without full proof")
    if not payload.get("remainingRuntimeProof"):
        errors.append("ledger must list remaining runtime proof")

    slices = payload.get("slices")
    if not isinstance(slices, list):
        return errors + ["ledger slices must be a list"]

    seen_slices: set[int] = set()
    for item in slices:
        if not isinstance(item, dict):
            errors.append(f"ledger slice entry must be an object: {item!r}")
            continue
        slice_number = item.get("slice")
        if not isinstance(slice_number, int):
            errors.append(f"ledger slice entry has invalid slice number: {item!r}")
            continue
        if slice_number in seen_slices:
            errors.append(f"duplicate RFC-0083 slice in ledger: {slice_number}")
        seen_slices.add(slice_number)
        _require_non_empty_string(item, "title", errors, slice_number)
        _require_non_empty_string(item, "validationLane", errors, slice_number)
        status = item.get("status")
        if status not in VALID_STATUSES:
            errors.append(f"slice {slice_number} status must be one of {sorted(VALID_STATUSES)}")
        artifacts = item.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            errors.append(f"slice {slice_number} must list artifacts")
            continue
        for artifact in artifacts:
            if not isinstance(artifact, str) or not artifact.strip():
                errors.append(f"slice {slice_number} has invalid artifact path: {artifact!r}")
                continue
            if Path(artifact).is_absolute():
                errors.append(f"slice {slice_number} artifact must be repo-relative: {artifact}")
                continue
            if not (repo_root / artifact).exists():
                errors.append(f"slice {slice_number} artifact does not exist: {artifact}")

    missing_slices = EXPECTED_SLICES - seen_slices
    extra_slices = seen_slices - EXPECTED_SLICES
    if missing_slices:
        errors.append("ledger is missing slice(s): " + ", ".join(map(str, sorted(missing_slices))))
    if extra_slices:
        errors.append(
            "ledger contains unknown slice(s): " + ", ".join(map(str, sorted(extra_slices)))
        )
    return errors


def _require_non_empty_string(
    item: dict[str, Any], field_name: str, errors: list[str], slice_number: int
) -> None:
    value = item.get(field_name)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"slice {slice_number} must define non-empty {field_name}")


def main() -> int:
    errors = evaluate_ledger(load_ledger())
    if errors:
        print("RFC-0083 closure guard failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("RFC-0083 closure guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
