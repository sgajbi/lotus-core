"""Audit bounded lot-book and current-position quantity parity."""

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

from portfolio_common.database_runtime_identity import (  # noqa: E402
    database_runtime_identity_scope,
)
from portfolio_common.db import get_async_engine  # noqa: E402

from src.services.portfolio_transaction_processing_service.app.application import (  # noqa: E402
    AuditLotPositionParityCommand,
    AuditLotPositionParityResult,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (  # noqa: E402, E501
    LotPositionParityKey,
)
from src.services.portfolio_transaction_processing_service.app.runtime.dependency_composition import (  # noqa: E402, E501
    build_audit_lot_position_parity_use_case,
)

SCHEMA_VERSION = "lotus-core.lot-position-parity.v1"


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, LotPositionParityKey):
        return asdict(value)
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


def build_report(result: AuditLotPositionParityResult) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "summary": {
            "candidate_count": len(result.assessments),
            "current_count": result.current_count,
            "drifted_count": result.drifted_count,
        },
        "next_cursor": _json_value(result.next_cursor),
        "assessments": [_json_value(asdict(item)) for item in result.assessments],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
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
    with database_runtime_identity_scope("lot-position-parity-audit"):
        try:
            after = (
                LotPositionParityKey(args.after_portfolio_id, args.after_security_id)
                if args.after_portfolio_id
                else None
            )
            result = await build_audit_lot_position_parity_use_case().execute(
                AuditLotPositionParityCommand(
                    portfolio_id=args.portfolio_id,
                    limit=args.limit,
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
    return 1 if report["summary"]["drifted_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
