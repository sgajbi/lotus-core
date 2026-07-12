"""Audit or repair historical AVCO pool and source-lot state."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
for source_root in (REPO_ROOT, REPO_ROOT / "src" / "libs" / "portfolio-common"):
    sys.path.insert(0, str(source_root))

from portfolio_common.db import get_async_engine  # noqa: E402

from src.services.portfolio_transaction_processing_service.app.application import (  # noqa: E402
    ReconcileAverageCostPoolsCommand,
    ReconcileAverageCostPoolsResult,
)
from src.services.portfolio_transaction_processing_service.app.domain import (  # noqa: E402
    AverageCostPoolKey,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (  # noqa: E402
    build_reconcile_average_cost_pools_use_case,
)

SCHEMA_VERSION = "lotus-core.average-cost-pool-reconciliation.v1"


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, AverageCostPoolKey):
        return asdict(value)
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


def build_report(result: ReconcileAverageCostPoolsResult) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "mode": "apply" if result.apply else "dry_run",
        "summary": {
            "candidate_count": len(result.assessments),
            "current_count": result.current_count,
            "drifted_count": result.drifted_count,
            "reconciled_count": result.reconciled_count,
            "failed_count": result.failed_count,
        },
        "next_cursor": _json_value(result.next_cursor),
        "assessments": [_json_value(asdict(assessment)) for assessment in result.assessments],
    }


def exit_code(report: dict[str, Any]) -> int:
    summary = report["summary"]
    if summary["failed_count"]:
        return 2
    if report["mode"] == "dry_run" and summary["drifted_count"]:
        return 1
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist replay-proven repairs; default is a read-only dry run.",
    )
    parser.add_argument("--portfolio-id")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--after-portfolio-id")
    parser.add_argument("--after-security-id")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if bool(args.after_portfolio_id) != bool(args.after_security_id):
        parser.error("both --after-portfolio-id and --after-security-id are required for a cursor")
    return args


async def run(args: argparse.Namespace) -> dict[str, Any]:
    try:
        after = (
            AverageCostPoolKey(args.after_portfolio_id, args.after_security_id)
            if args.after_portfolio_id
            else None
        )
        result = await build_reconcile_average_cost_pools_use_case().execute(
            ReconcileAverageCostPoolsCommand(
                apply=args.apply,
                limit=args.limit,
                portfolio_id=args.portfolio_id,
                after=after,
            )
        )
        return build_report(result)
    finally:
        await get_async_engine().dispose()


def main() -> int:
    args = parse_args()
    report = asyncio.run(run(args))
    rendered = json.dumps(report, indent=2, sort_keys=True, allow_nan=False)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n", encoding="utf-8")
    print(rendered)
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
