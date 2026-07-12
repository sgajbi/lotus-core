# CR-490: API Query Index And Partition Review

Date: 2026-05-28

## Scope

Database model, Alembic migration, and partition-readiness posture for high-volume `lotus-core`
API and internal calculation query paths.

## Finding

Recent correctness work moved multiple read paths to normalized instrument predicates such as
`trim(security_id)` and `trim(settlement_cash_instrument_id)`, while preserving raw
`portfolio_id` equality for the calling portfolio. The previous normalized indexes were optimized
for `trim(portfolio_id)` plus `trim(security_id)`, which remains useful for dirty caller input, but
does not perfectly match the hottest query-service and reporting shapes.

Reviewed hot paths include:

1. transaction ledger pagination, cost evidence, tax evidence, linked-group lookup, and cash-account
   fallback queries,
2. latest position-history and daily-snapshot reconstruction,
3. position-state enrichment joins,
4. reporting cash-account master ordering,
5. instrument lookthrough component lookup by normalized parent security.

Partitioning is relevant for long-history fact tables, but no current Alembic migration converts
Core fact tables into PostgreSQL partitioned parents. Converting populated authoritative tables is
a higher-risk physical storage migration because it changes table DDL, constraint shape, index
inheritance, migration sequencing, rollback posture, and operational runbook expectations.

## Change

Added SQLAlchemy model indexes and Alembic migration
`a0b1c2d3e4f5_perf_add_api_query_hot_path_indexes.py` for query shapes that are already present:

1. `position_history`: raw portfolio, normalized security, latest position date/id, and epoch,
2. `daily_position_snapshots`: raw portfolio, normalized security, latest snapshot date/id, and
   epoch,
3. `position_state`: raw portfolio, normalized security, and epoch for latest-row enrichment joins,
4. `transactions`: raw portfolio with date/id ordering for default ledger paging,
5. `transactions`: raw portfolio, normalized security, and date/id ordering for ledger/evidence
   filters,
6. `transactions`: raw portfolio, normalized settlement cash instrument, and date/id ordering for
   cash-account fallback,
7. `transactions`: raw portfolio, linked transaction group, and date/id ordering for grouped
   event evidence,
8. `cash_account_masters`: portfolio, account currency, and cash-account id ordering,
9. `instrument_lookthrough_components`: normalized parent security, effective window, and
   normalized component ordering.

Added `scripts/db_partition_advisor.py` as a conservative partition-readiness utility:

1. identifies partition candidates: `transactions`, `position_history`, `daily_position_snapshots`,
   `cashflows`, `position_timeseries`, `portfolio_timeseries`, and `market_prices`,
2. recommends monthly range partition keys aligned to the dominant date-window predicates,
3. emits future monthly `CREATE TABLE IF NOT EXISTS ... PARTITION OF ...` DDL,
4. can inspect PostgreSQL partition status when `DATABASE_URL` is provided,
5. will execute partition creation only for tables that already exist as partitioned parents.

## Partition Disposition

Do not convert live Core fact tables to partitioned parents in this index slice.

Recommended partition priority if production telemetry shows sustained row-count or latency
pressure after index rollout:

1. `transactions` by monthly `transaction_date`,
2. `position_history` by monthly `position_date`,
3. `daily_position_snapshots` by monthly `date`,
4. `cashflows` by monthly `cashflow_date`,
5. `position_timeseries` and `portfolio_timeseries` by monthly `date`,
6. `market_prices` by monthly `price_date` once vendor history depth justifies the operational
   cost.

Automation should run as a scheduled DB maintenance step after a table has been converted through a
separate governed migration into a PostgreSQL partitioned parent. Until then, the advisor is
planning and readiness evidence, not a hidden schema mutation path.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/scripts/test_db_partition_advisor.py -q`
2. `python -m pytest tests/unit/libs/portfolio-common tests/unit/libs/portfolio_common -q`
3. `python -m pytest tests/unit/scripts/test_db_partition_advisor.py -q`
4. `python -m alembic heads`
5. `python scripts/migration_contract_check.py --mode alembic-sql`
6. `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py tests/unit/libs/portfolio-common/test_database_models.py alembic/versions/a0b1c2d3e4f5_perf_add_api_query_hot_path_indexes.py scripts/db_partition_advisor.py tests/unit/scripts/test_db_partition_advisor.py`
7. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/database_models.py tests/unit/libs/portfolio-common/test_database_models.py alembic/versions/a0b1c2d3e4f5_perf_add_api_query_hot_path_indexes.py scripts/db_partition_advisor.py tests/unit/scripts/test_db_partition_advisor.py`
8. `python scripts/db_partition_advisor.py --as-of 2026-05-28 --horizon-months 1`
9. `git diff --check`
10. `../lotus-platform/automation/Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core`

Results:

1. Focused index and partition-advisor proof: `9 passed`
2. Portfolio-common unit pack: `498 passed`
3. Partition-advisor unit proof: `3 passed`
4. Alembic head proof: `a0b1c2d3e4f5 (head)`
5. Migration contract smoke: passed
6. Touched-surface ruff: passed
7. Touched-surface format check: passed
8. Partition-advisor report generation: passed
9. Diff hygiene: passed
10. Wiki check: expected branch-local drift on `Database-Migrations.md`; publish after merge to
    `main`

## Closure

Status: Hardened.

No API route shape or platform contract changed. Repo-local wiki source was updated to record the
partition advisor and the deliberate no-implicit-partitioning policy. The hot API and internal
calculation read paths now have index support aligned to the actual repository query predicates,
while partitioning remains governed by explicit storage-migration evidence rather than hidden
runtime mutation.
