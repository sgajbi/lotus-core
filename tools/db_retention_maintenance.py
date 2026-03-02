from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from portfolio_common.db import SessionLocal


@dataclass(frozen=True)
class RetentionRule:
    name: str
    count_sql: str
    delete_sql: str


def _rules(args: argparse.Namespace) -> list[RetentionRule]:
    return [
        RetentionRule(
            name="processed_events",
            count_sql=(
                "SELECT count(*) FROM processed_events "
                "WHERE processed_at < now() - make_interval(days => :days)"
            ),
            delete_sql=(
                "DELETE FROM processed_events "
                "WHERE processed_at < now() - make_interval(days => :days)"
            ),
        ),
        RetentionRule(
            name="outbox_events_processed",
            count_sql=(
                "SELECT count(*) FROM outbox_events "
                "WHERE status = 'PROCESSED' "
                "AND processed_at IS NOT NULL "
                "AND processed_at < now() - make_interval(days => :days)"
            ),
            delete_sql=(
                "DELETE FROM outbox_events "
                "WHERE status = 'PROCESSED' "
                "AND processed_at IS NOT NULL "
                "AND processed_at < now() - make_interval(days => :days)"
            ),
        ),
        RetentionRule(
            name="portfolio_valuation_jobs_terminal",
            count_sql=(
                "SELECT count(*) FROM portfolio_valuation_jobs "
                "WHERE status IN ('COMPLETE', 'FAILED', 'SKIPPED_NO_POSITION') "
                "AND updated_at < now() - make_interval(days => :days)"
            ),
            delete_sql=(
                "DELETE FROM portfolio_valuation_jobs "
                "WHERE status IN ('COMPLETE', 'FAILED', 'SKIPPED_NO_POSITION') "
                "AND updated_at < now() - make_interval(days => :days)"
            ),
        ),
        RetentionRule(
            name="portfolio_aggregation_jobs_terminal",
            count_sql=(
                "SELECT count(*) FROM portfolio_aggregation_jobs "
                "WHERE status IN ('COMPLETE', 'FAILED') "
                "AND updated_at < now() - make_interval(days => :days)"
            ),
            delete_sql=(
                "DELETE FROM portfolio_aggregation_jobs "
                "WHERE status IN ('COMPLETE', 'FAILED') "
                "AND updated_at < now() - make_interval(days => :days)"
            ),
        ),
        RetentionRule(
            name="analytics_export_jobs_terminal",
            count_sql=(
                "SELECT count(*) FROM analytics_export_jobs "
                "WHERE status IN ('completed', 'failed') "
                "AND completed_at IS NOT NULL "
                "AND completed_at < now() - make_interval(days => :days)"
            ),
            delete_sql=(
                "DELETE FROM analytics_export_jobs "
                "WHERE status IN ('completed', 'failed') "
                "AND completed_at IS NOT NULL "
                "AND completed_at < now() - make_interval(days => :days)"
            ),
        ),
        RetentionRule(
            name="consumer_dlq_replay_audit_completed",
            count_sql=(
                "SELECT count(*) FROM consumer_dlq_replay_audit "
                "WHERE completed_at IS NOT NULL "
                "AND completed_at < now() - make_interval(days => :days)"
            ),
            delete_sql=(
                "DELETE FROM consumer_dlq_replay_audit "
                "WHERE completed_at IS NOT NULL "
                "AND completed_at < now() - make_interval(days => :days)"
            ),
        ),
    ]


def run(args: argparse.Namespace) -> int:
    days_by_rule = {
        "processed_events": args.processed_events_days,
        "outbox_events_processed": args.outbox_processed_days,
        "portfolio_valuation_jobs_terminal": args.valuation_jobs_days,
        "portfolio_aggregation_jobs_terminal": args.aggregation_jobs_days,
        "analytics_export_jobs_terminal": args.analytics_exports_days,
        "consumer_dlq_replay_audit_completed": args.dlq_replay_audit_days,
    }

    summary: dict[str, dict[str, int | bool]] = {}

    try:
        with SessionLocal() as db:
            for rule in _rules(args):
                days = days_by_rule[rule.name]
                eligible = int(db.execute(text(rule.count_sql), {"days": days}).scalar() or 0)
                deleted = 0
                if not args.dry_run and eligible > 0:
                    deleted = int(db.execute(text(rule.delete_sql), {"days": days}).rowcount or 0)
                summary[rule.name] = {
                    "days": days,
                    "eligible_rows": eligible,
                    "deleted_rows": deleted,
                    "dry_run": args.dry_run,
                }

            if args.dry_run:
                db.rollback()
            else:
                db.commit()
    except OperationalError as exc:
        error_payload = {
            "error": "database_connection_failed",
            "message": str(exc),
            "hint": (
                "Ensure PostgreSQL is reachable. For local host execution, set HOST_DATABASE_URL, "
                "for example: postgresql://user:password@localhost:5432/portfolio_db"
            ),
        }
        print(json.dumps(error_payload, indent=2, sort_keys=True))
        return 2

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Lotus-Core retention maintenance for terminal job/audit/idempotency tables. "
            "Use --no-dry-run to execute deletions."
        )
    )
    parser.set_defaults(dry_run=True)
    parser.add_argument("--dry-run", dest="dry_run", action="store_true")
    parser.add_argument("--no-dry-run", dest="dry_run", action="store_false")

    parser.add_argument("--processed-events-days", type=int, default=30)
    parser.add_argument("--outbox-processed-days", type=int, default=14)
    parser.add_argument("--valuation-jobs-days", type=int, default=30)
    parser.add_argument("--aggregation-jobs-days", type=int, default=30)
    parser.add_argument("--analytics-exports-days", type=int, default=30)
    parser.add_argument("--dlq-replay-audit-days", type=int, default=60)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
