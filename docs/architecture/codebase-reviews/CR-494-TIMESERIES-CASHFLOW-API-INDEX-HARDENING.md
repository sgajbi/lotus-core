# CR-494: Timeseries Cashflow API Index Hardening

Date: 2026-05-28

## Scope

Analytics time-series and position-cashflow lookup indexes used by query-service and calculation
paths.

## Finding

Position time-series APIs commonly filter by raw `portfolio_id` and a date window across all
securities. The table primary key starts with `(portfolio_id, security_id, date, epoch)`, which is
excellent for a single security but weaker for portfolio-wide date windows because `date` comes
after `security_id`.

Position cashflow analytics also use raw `portfolio_id` with normalized `security_id` and
`cashflow_date` predicates. Existing normalized indexes supported `trim(portfolio_id)` and
`trim(security_id)`, but not the raw-portfolio query shape used by the API path.

## Change

Added SQLAlchemy model indexes and Alembic migration
`c0d1e2f3a4b5_perf_add_timeseries_cashflow_api_indexes.py`:

1. `ix_pos_ts_port_date_norm_sec_epoch` on
   `position_timeseries(portfolio_id, date, trim(security_id), epoch DESC)`,
2. `ix_cashflows_port_norm_sec_date_epoch` on
   `cashflows(portfolio_id, trim(security_id), cashflow_date, epoch DESC)`.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py tests/unit/libs/portfolio-common/test_database_models.py alembic/versions/c0d1e2f3a4b5_perf_add_timeseries_cashflow_api_indexes.py`
5. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/database_models.py tests/unit/libs/portfolio-common/test_database_models.py alembic/versions/c0d1e2f3a4b5_perf_add_timeseries_cashflow_api_indexes.py`

Results:

1. Focused database model proof: `6 passed`
2. Alembic head proof: `c0d1e2f3a4b5 (head)`
3. Migration contract smoke: passed
4. Touched-surface ruff: passed
5. Touched-surface format check: passed

## Closure

Status: Hardened.

No API route shape, wiki source, or platform contract change was required. Portfolio-wide
time-series reads and position-cashflow analytics now have index support aligned to their actual
raw-portfolio query predicates.
