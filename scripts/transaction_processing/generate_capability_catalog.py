"""Refresh registry-owned entries in the transaction capability catalog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from portfolio_common.domain.transaction.type_registry import TRANSACTION_TYPE_REGISTRY

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = Path("contracts/transaction-processing/transaction-capability-catalog.v1.json")
GAP_ISSUES_BY_TRANSACTION_TYPE = {
    "ACCRETION": 478,
    "ADJUSTMENT": 719,
    "AMORTIZATION": 478,
    "CALL_REDEMPTION": 477,
    "CONVERSION_EVENT": 479,
    "CONVERSION_IN": 479,
    "CONVERSION_OUT": 479,
    "EXERCISE_IN": 479,
    "EXERCISE_OUT": 479,
    "FEE": 719,
    "MATURITY_REDEMPTION": 477,
    "OTHER": 718,
    "PARTIAL_REDEMPTION": 477,
    "RIGHTS_ADJUSTMENT": 719,
    "RIGHTS_ANNOUNCE": 719,
    "STRIKE_PAYMENT": 479,
    "TAX": 719,
}


def build_transaction_type_entries() -> list[dict[str, object]]:
    """Build a stable public snapshot of transaction registry support posture."""

    return [
        {
            "code": code,
            "lifecycle_family": definition.lifecycle_family,
            "economic_role": definition.economic_role,
            "support_status": definition.calculation_support_status,
            "production_booking_allowed": definition.production_booking_allowed,
            "gap_issue": GAP_ISSUES_BY_TRANSACTION_TYPE.get(code),
        }
        for code, definition in TRANSACTION_TYPE_REGISTRY.items()
    ]


def refresh_catalog(path: Path) -> bool:
    """Refresh generated registry entries and return whether file content changed."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["transaction_types"] = build_transaction_type_entries()
    rendered = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    previous = path.read_text(encoding="utf-8")
    if rendered == previous:
        return False
    path.write_text(rendered, encoding="utf-8")
    return True


def main() -> int:
    """Refresh the configured catalog file."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    path = args.output if args.output.is_absolute() else REPO_ROOT / args.output
    changed = refresh_catalog(path)
    print(f"transaction capability catalog {'updated' if changed else 'current'}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
