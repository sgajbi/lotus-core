# CR-142 Replay Ordering Index Review

## Scope
- instrument replay trigger claim ordering
- durable `RESET_WATERMARKS` worker claim ordering

## Finding
The replay pipeline now has deterministic oldest-impact-first ordering on both the trigger side and the durable worker side, but the database still lacked indexes that support those exact orderings. Under backlog, that forces unnecessary scans and sorts on active replay control tables.

## Fix
- Added index on `instrument_reprocessing_state` for the scheduler-facing trigger claim order:
  - `(earliest_impacted_date, updated_at, security_id)`
- Added a partial expression index on pending `RESET_WATERMARKS` jobs for the worker claim order:
  - `((payload->>'earliest_impacted_date')::date, created_at, id)`
  - only where `job_type = 'RESET_WATERMARKS' AND status = 'PENDING'`

## Validation
- `python scripts/migration_contract_check.py --mode alembic-sql`
- `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py alembic/versions/f2b3c4d5e6f7_perf_add_replay_ordering_indexes.py`

## Status
- Hardened
