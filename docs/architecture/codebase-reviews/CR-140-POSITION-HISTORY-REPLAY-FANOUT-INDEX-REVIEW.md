# CR-140 Position History Replay Fanout Index Review

## Scope
- `PositionHistory` access path used by `find_portfolios_holding_security_on_date(...)`
- durable replay fanout performance

## Finding
The replay fanout query is now business-correct and epoch-fenced, but it still relied on a portfolio-oriented index:
- `(portfolio_id, security_id, epoch, position_date)`

That is not the right access path for the worker-facing query, which starts from:
- `security_id`
- current `epoch`
- latest `position_date` / `id`
- then projects `portfolio_id`

## Fix
- Added a replay-fanout-oriented covering index on `position_history`:
  - `(security_id, epoch, position_date DESC, id DESC, portfolio_id)`
- Kept the existing portfolio-oriented index because it still serves other history reads.

## Validation
- `python scripts/migration_contract_check.py --mode alembic-sql`
- `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py alembic/versions/f1b2c3d4e5f6_perf_add_position_history_replay_fanout_index.py`

## Status
- Hardened
