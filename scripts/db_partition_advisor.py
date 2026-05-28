"""Review and maintain PostgreSQL range partitions for lotus-core fact tables.

The script is intentionally conservative: it can generate future monthly
partition DDL for known high-volume tables, but execution is allowed only when
the target table is already a PostgreSQL partitioned parent. Converting an
existing populated table into a partitioned parent remains a governed migration.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from sqlalchemy import create_engine, text

_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


@dataclass(frozen=True)
class PartitionCandidate:
    table_name: str
    partition_column: str
    cadence: str
    priority: str
    reason: str


@dataclass(frozen=True)
class PartitionStatus:
    table_name: str
    is_partitioned_parent: bool
    partition_count: int
    approximate_rows: int | None


PARTITION_CANDIDATES: tuple[PartitionCandidate, ...] = (
    PartitionCandidate(
        table_name="transactions",
        partition_column="transaction_date",
        cadence="monthly",
        priority="high",
        reason=(
            "Transaction ledger, realized tax, cash fallback, cost evidence, and "
            "default API pagination all scan by portfolio/date windows."
        ),
    ),
    PartitionCandidate(
        table_name="position_history",
        partition_column="position_date",
        cadence="monthly",
        priority="high",
        reason=(
            "Position replay, latest holding reconstruction, and calculation "
            "lookbacks are date-windowed and can grow quickly for active books."
        ),
    ),
    PartitionCandidate(
        table_name="daily_position_snapshots",
        partition_column="date",
        cadence="monthly",
        priority="high",
        reason=(
            "Latest holdings, reporting snapshots, and valuation maps repeatedly "
            "seek portfolio/security rows by as-of date."
        ),
    ),
    PartitionCandidate(
        table_name="cashflows",
        partition_column="cashflow_date",
        cadence="monthly",
        priority="medium",
        reason=(
            "Cashflow evidence and portfolio-flow calculations are date-windowed "
            "and should stay pruneable as history deepens."
        ),
    ),
    PartitionCandidate(
        table_name="position_timeseries",
        partition_column="date",
        cadence="monthly",
        priority="medium",
        reason=(
            "Position-level analytics history is naturally date-ranged and can "
            "be pruned by reporting or analytics windows."
        ),
    ),
    PartitionCandidate(
        table_name="portfolio_timeseries",
        partition_column="date",
        cadence="monthly",
        priority="medium",
        reason=(
            "Portfolio-level analytics history is naturally date-ranged and "
            "supports period analytics and reporting windows."
        ),
    ),
    PartitionCandidate(
        table_name="market_prices",
        partition_column="price_date",
        cadence="monthly",
        priority="medium",
        reason=(
            "Market-price lookup is security/date oriented; range partitions can "
            "help once vendor history becomes large."
        ),
    ),
)


def _quote_identifier(identifier: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(identifier):
        raise ValueError(f"Unsafe PostgreSQL identifier: {identifier!r}")
    return f'"{identifier}"'


def month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def add_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    return date(month_index // 12, month_index % 12 + 1, 1)


def partition_table_name(table_name: str, month: date) -> str:
    return f"{table_name}_y{month.year:04d}m{month.month:02d}"


def generate_monthly_partition_sql(
    candidate: PartitionCandidate,
    *,
    start_month: date,
    months: int,
) -> list[str]:
    if candidate.cadence != "monthly":
        raise ValueError(f"Unsupported partition cadence: {candidate.cadence}")
    if months < 1:
        raise ValueError("months must be at least 1")

    start_month = month_start(start_month)
    parent = _quote_identifier(candidate.table_name)
    statements: list[str] = []
    for offset in range(months):
        lower = add_months(start_month, offset)
        upper = add_months(start_month, offset + 1)
        partition = _quote_identifier(partition_table_name(candidate.table_name, lower))
        statements.append(
            f"CREATE TABLE IF NOT EXISTS {partition} PARTITION OF {parent} "
            f"FOR VALUES FROM ('{lower.isoformat()}') TO ('{upper.isoformat()}');"
        )
    return statements


def inspect_partition_status(database_url: str) -> dict[str, PartitionStatus]:
    engine = create_engine(database_url)
    query = text(
        """
        SELECT
            c.relname AS table_name,
            pt.partrelid IS NOT NULL AS is_partitioned_parent,
            COALESCE(child_counts.partition_count, 0) AS partition_count,
            COALESCE(stats.n_live_tup, 0) AS approximate_rows
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_partitioned_table pt ON pt.partrelid = c.oid
        LEFT JOIN pg_stat_user_tables stats ON stats.relid = c.oid
        LEFT JOIN (
            SELECT inhparent, count(*) AS partition_count
            FROM pg_inherits
            GROUP BY inhparent
        ) child_counts ON child_counts.inhparent = c.oid
        WHERE n.nspname = current_schema()
          AND c.relname = :table_name
        """
    )

    statuses: dict[str, PartitionStatus] = {}
    with engine.connect() as connection:
        for candidate in PARTITION_CANDIDATES:
            row = connection.execute(query, {"table_name": candidate.table_name}).mappings().first()
            if row is None:
                statuses[candidate.table_name] = PartitionStatus(
                    table_name=candidate.table_name,
                    is_partitioned_parent=False,
                    partition_count=0,
                    approximate_rows=None,
                )
                continue
            statuses[candidate.table_name] = PartitionStatus(
                table_name=row["table_name"],
                is_partitioned_parent=bool(row["is_partitioned_parent"]),
                partition_count=int(row["partition_count"]),
                approximate_rows=int(row["approximate_rows"]),
            )
    return statuses


def build_report(
    *,
    as_of: date,
    horizon_months: int,
    statuses: dict[str, PartitionStatus] | None = None,
) -> dict[str, Any]:
    start_month = month_start(as_of)
    report_candidates: list[dict[str, Any]] = []
    for candidate in PARTITION_CANDIDATES:
        status = statuses.get(candidate.table_name) if statuses else None
        partition_sql = generate_monthly_partition_sql(
            candidate,
            start_month=start_month,
            months=horizon_months,
        )
        report_candidates.append(
            {
                **asdict(candidate),
                "recommended_partition_key": candidate.partition_column,
                "automation_mode": "monthly-range-create-if-parent-partitioned",
                "status": asdict(status) if status else None,
                "future_partition_sql": partition_sql,
            }
        )
    return {
        "generated_for_month": start_month.isoformat(),
        "horizon_months": horizon_months,
        "execution_policy": (
            "Generate SQL for planning, but execute only for tables already converted "
            "to partitioned parents."
        ),
        "candidates": report_candidates,
    }


def execute_partition_sql(database_url: str, report: dict[str, Any]) -> list[str]:
    partitioned_tables = {
        candidate["table_name"]
        for candidate in report["candidates"]
        if candidate.get("status", {}).get("is_partitioned_parent") is True
    }
    statements = [
        statement
        for candidate in report["candidates"]
        if candidate["table_name"] in partitioned_tables
        for statement in candidate["future_partition_sql"]
    ]

    if not statements:
        return []

    engine = create_engine(database_url)
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
    return statements


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="PostgreSQL URL. Defaults to DATABASE_URL. Required for --inspect or --execute.",
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Inspect current PostgreSQL partition status for known fact-table candidates.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Create future partitions only for tables already partitioned in PostgreSQL.",
    )
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=date.today(),
        help="Month anchor for generated partition DDL. Defaults to today.",
    )
    parser.add_argument(
        "--horizon-months",
        type=int,
        default=3,
        help="Number of future monthly partitions to include.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    statuses = None
    if args.inspect or args.execute:
        if not args.database_url:
            raise SystemExit("--database-url or DATABASE_URL is required with --inspect/--execute")
        statuses = inspect_partition_status(args.database_url)

    report = build_report(
        as_of=args.as_of,
        horizon_months=args.horizon_months,
        statuses=statuses,
    )
    executed = execute_partition_sql(args.database_url, report) if args.execute else []
    if args.execute:
        report["executed_statement_count"] = len(executed)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
