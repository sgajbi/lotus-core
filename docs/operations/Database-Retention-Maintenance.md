# Database Retention Maintenance

## Purpose
This runbook defines safe cleanup of high-churn terminal tables in Lotus-Core to keep operational queries fast and prevent unbounded storage growth.

## Script
`tools/db_retention_maintenance.py`

## Default Scope
The script targets only terminal/archival-safe rows:
- `processed_events`
- `outbox_events` where `status = PROCESSED`
- `portfolio_valuation_jobs` where `status in (COMPLETE, FAILED, SKIPPED_NO_POSITION, SKIPPED_SUPERSEDED)`
- `portfolio_aggregation_jobs` where `status in (COMPLETE, FAILED)`
- `analytics_export_jobs` where `status in (completed, failed)`
- `consumer_dlq_replay_audit` where `completed_at is not null`

## Usage
Dry run (default):
```bash
python tools/db_retention_maintenance.py --dry-run
```

Execute cleanup:
```bash
python tools/db_retention_maintenance.py --no-dry-run
```

Example with custom windows:
```bash
python tools/db_retention_maintenance.py --dry-run \
  --processed-events-days 14 \
  --outbox-processed-days 7 \
  --valuation-jobs-days 21 \
  --aggregation-jobs-days 21 \
  --analytics-exports-days 30 \
  --dlq-replay-audit-days 90
```

## Safety Notes
- Always run dry-run first and review eligible row counts.
- Schedule in low-traffic windows.
- Keep backups/point-in-time recovery enabled at database level.
- This script intentionally does not touch active queue rows (`PENDING`, `PROCESSING`, `accepted`, `running`).
