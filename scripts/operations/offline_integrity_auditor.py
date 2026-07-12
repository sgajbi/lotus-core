"""Offline ledger-vs-snapshot integrity auditor for RFC-010 D02.

Compares holdings reconstructed from transactions against the latest persisted
daily position snapshots (per portfolio/security) as of a target date.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, text


@dataclass(slots=True, frozen=True)
class PositionKey:
    portfolio_id: str
    security_id: str


@dataclass(slots=True)
class LedgerRow:
    portfolio_id: str
    security_id: str
    transaction_type: str
    quantity: Decimal
    business_date: date


@dataclass(slots=True)
class SnapshotRow:
    portfolio_id: str
    security_id: str
    quantity: Decimal
    snapshot_date: date
    epoch: int


@dataclass(slots=True)
class Mismatch:
    portfolio_id: str
    security_id: str
    ledger_quantity: str
    snapshot_quantity: str
    delta_quantity: str
    classification: str


@dataclass(slots=True)
class IntegrityAuditResult:
    run_id: str
    generated_at: str
    as_of_date: str
    tolerance: str
    ledger_position_count: int
    snapshot_position_count: int
    compared_position_count: int
    mismatch_count: int
    checks_passed: bool
    mismatches: list[Mismatch]


def _signed_quantity(transaction_type: str, quantity: Decimal) -> Decimal:
    tx_type = transaction_type.strip().upper()
    if tx_type in {"SELL"}:
        return -quantity
    if tx_type in {"BUY"}:
        return quantity
    # Non-position-affecting or unsupported types are ignored by default.
    return Decimal("0")


def _aggregate_ledger_positions(rows: list[LedgerRow]) -> dict[PositionKey, Decimal]:
    aggregated: dict[PositionKey, Decimal] = {}
    for row in rows:
        key = PositionKey(portfolio_id=row.portfolio_id, security_id=row.security_id)
        aggregated[key] = aggregated.get(key, Decimal("0")) + _signed_quantity(
            row.transaction_type, row.quantity
        )
    # Drop exact zero positions to reduce noise.
    return {key: qty for key, qty in aggregated.items() if qty != Decimal("0")}


def _latest_snapshot_positions(rows: list[SnapshotRow]) -> dict[PositionKey, Decimal]:
    latest: dict[PositionKey, SnapshotRow] = {}
    for row in rows:
        key = PositionKey(portfolio_id=row.portfolio_id, security_id=row.security_id)
        prior = latest.get(key)
        if prior is None:
            latest[key] = row
            continue
        if row.snapshot_date > prior.snapshot_date:
            latest[key] = row
            continue
        if row.snapshot_date == prior.snapshot_date and row.epoch > prior.epoch:
            latest[key] = row
    return {
        PositionKey(portfolio_id=k.portfolio_id, security_id=k.security_id): v.quantity
        for k, v in latest.items()
    }


def _compare_positions(
    ledger: dict[PositionKey, Decimal],
    snapshot: dict[PositionKey, Decimal],
    *,
    tolerance: Decimal,
) -> list[Mismatch]:
    mismatches: list[Mismatch] = []
    all_keys = set(ledger.keys()) | set(snapshot.keys())
    for key in sorted(all_keys, key=lambda x: (x.portfolio_id, x.security_id)):
        ledger_qty = ledger.get(key, Decimal("0"))
        snapshot_qty = snapshot.get(key, Decimal("0"))
        delta = snapshot_qty - ledger_qty
        if abs(delta) <= tolerance:
            continue
        if key not in snapshot:
            classification = "missing_snapshot"
        elif key not in ledger:
            classification = "missing_ledger"
        else:
            classification = "quantity_mismatch"
        mismatches.append(
            Mismatch(
                portfolio_id=key.portfolio_id,
                security_id=key.security_id,
                ledger_quantity=str(ledger_qty),
                snapshot_quantity=str(snapshot_qty),
                delta_quantity=str(delta),
                classification=classification,
            )
        )
    return mismatches


def _load_ledger_rows(*, db_url: str, as_of_date: date) -> list[LedgerRow]:
    query = text(
        """
        SELECT
            portfolio_id,
            security_id,
            transaction_type,
            quantity,
            DATE(transaction_date) AS business_date
        FROM transactions
        WHERE DATE(transaction_date) <= :as_of_date
        """
    )
    engine = create_engine(db_url)
    with engine.connect() as conn:
        rows = conn.execute(query, {"as_of_date": as_of_date}).mappings().all()
    return [
        LedgerRow(
            portfolio_id=str(row["portfolio_id"]),
            security_id=str(row["security_id"]),
            transaction_type=str(row["transaction_type"]),
            quantity=Decimal(str(row["quantity"])),
            business_date=row["business_date"],
        )
        for row in rows
    ]


def _load_snapshot_rows(*, db_url: str, as_of_date: date) -> list[SnapshotRow]:
    query = text(
        """
        SELECT
            portfolio_id,
            security_id,
            quantity,
            date AS snapshot_date,
            epoch
        FROM daily_position_snapshots
        WHERE date <= :as_of_date
        """
    )
    engine = create_engine(db_url)
    with engine.connect() as conn:
        rows = conn.execute(query, {"as_of_date": as_of_date}).mappings().all()
    return [
        SnapshotRow(
            portfolio_id=str(row["portfolio_id"]),
            security_id=str(row["security_id"]),
            quantity=Decimal(str(row["quantity"])),
            snapshot_date=row["snapshot_date"],
            epoch=int(row["epoch"]),
        )
        for row in rows
    ]


def run_audit(*, db_url: str, as_of_date: date, tolerance: Decimal) -> IntegrityAuditResult:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    ledger_rows = _load_ledger_rows(db_url=db_url, as_of_date=as_of_date)
    snapshot_rows = _load_snapshot_rows(db_url=db_url, as_of_date=as_of_date)

    ledger_positions = _aggregate_ledger_positions(ledger_rows)
    snapshot_positions = _latest_snapshot_positions(snapshot_rows)
    mismatches = _compare_positions(ledger_positions, snapshot_positions, tolerance=tolerance)
    compared_count = len(set(ledger_positions.keys()) | set(snapshot_positions.keys()))

    return IntegrityAuditResult(
        run_id=run_id,
        generated_at=datetime.now(UTC).isoformat(),
        as_of_date=as_of_date.isoformat(),
        tolerance=str(tolerance),
        ledger_position_count=len(ledger_positions),
        snapshot_position_count=len(snapshot_positions),
        compared_position_count=compared_count,
        mismatch_count=len(mismatches),
        checks_passed=len(mismatches) == 0,
        mismatches=mismatches,
    )


def _write_report(*, output_dir: Path, result: IntegrityAuditResult) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{result.run_id}-offline-integrity-audit.json"
    md_path = output_dir / f"{result.run_id}-offline-integrity-audit.md"

    payload = asdict(result)
    payload["mismatches"] = [asdict(item) for item in result.mismatches]
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        f"# Offline Integrity Audit {result.run_id}",
        "",
        f"- Overall passed: {result.checks_passed}",
        f"- As of date: `{result.as_of_date}`",
        f"- Tolerance: `{result.tolerance}`",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| ledger_position_count | {result.ledger_position_count} |",
        f"| snapshot_position_count | {result.snapshot_position_count} |",
        f"| compared_position_count | {result.compared_position_count} |",
        f"| mismatch_count | {result.mismatch_count} |",
    ]
    if result.mismatches:
        lines.extend(
            [
                "",
                "## Mismatch Sample",
                "",
                "| portfolio_id | security_id | ledger_quantity | snapshot_quantity | "
                "delta_quantity | classification |",
                "|---|---|---:|---:|---:|---|",
            ]
        )
        for item in result.mismatches[:50]:
            lines.append(
                f"| {item.portfolio_id} | {item.security_id} | {item.ledger_quantity} | "
                f"{item.snapshot_quantity} | {item.delta_quantity} | {item.classification} |"
            )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run offline ledger-vs-snapshot integrity audit.")
    parser.add_argument(
        "--db-url",
        default=os.getenv("HOST_DATABASE_URL", os.getenv("DATABASE_URL", "")),
        help="PostgreSQL URL (defaults to HOST_DATABASE_URL or DATABASE_URL).",
    )
    parser.add_argument("--as-of-date", default=date.today().isoformat(), help="YYYY-MM-DD")
    parser.add_argument("--tolerance", default="0.0000000001", help="Decimal tolerance.")
    parser.add_argument("--output-dir", default="output/task-runs")
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    if not args.db_url:
        raise ValueError("Database URL is required. Provide --db-url or set HOST_DATABASE_URL.")

    as_of = date.fromisoformat(args.as_of_date)
    tolerance = Decimal(args.tolerance)

    result = run_audit(db_url=args.db_url, as_of_date=as_of, tolerance=tolerance)
    output_dir = Path(args.output_dir).resolve()
    json_path, md_path = _write_report(output_dir=output_dir, result=result)
    print(f"Wrote offline integrity JSON report: {json_path}")
    print(f"Wrote offline integrity Markdown report: {md_path}")

    if args.enforce and not result.checks_passed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
