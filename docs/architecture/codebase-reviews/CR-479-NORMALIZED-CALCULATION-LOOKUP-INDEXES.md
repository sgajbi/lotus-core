# CR-479: Normalized Calculation Lookup Indexes

Date: 2026-05-28

## Scope

Database model and Alembic index posture for normalized calculation lookup predicates introduced
across cost, position, valuation, and timeseries repositories.

## Finding

The correctness slices normalized portfolio/security/transaction lookup predicates with
`trim(...)`, but most affected hot paths still only had raw-column indexes. Without matching
expression indexes, the repository changes could improve dirty-data tolerance while degrading
institutional-scale calculation latency and backlog drain behavior.

Enterprise-grade private banking calculation paths need both correctness and scalable query shape.
Normalized predicates used in hot reads should have explicit database support rather than relying
on table scans.

## Change

Added SQLAlchemy model indexes and Alembic migration
`9b0c1d2e3f4a_perf_add_normalized_calculation_lookup_indexes.py` for normalized lookup paths:

1. portfolio lookup by trimmed `portfolio_id`,
2. position-history replay/lookback by trimmed portfolio/security, epoch, date, and id,
3. daily-position snapshot lookup by trimmed portfolio/security, date, and epoch,
4. market-price lookup by trimmed security and price date,
5. transaction replay/cost-basis lookup by trimmed portfolio/security, transaction date, and
   transaction ID,
6. cashflow lookup by trimmed portfolio/security, cashflow date, and epoch,
7. position-lot lookup by trimmed portfolio/security,
8. position-timeseries lookup by trimmed portfolio/security, date, and epoch,
9. portfolio-timeseries lookup by trimmed portfolio, date, and epoch,
10. valuation-job status lookup by trimmed portfolio/security, valuation date, epoch, and status.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py -q`
2. `python -m pytest tests/unit/libs/portfolio-common tests/unit/libs/portfolio_common -q`
3. `python -m alembic heads`
4. `python scripts/migration_contract_check.py --mode alembic-sql`
5. `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py tests/unit/libs/portfolio-common/test_database_models.py alembic/versions/9b0c1d2e3f4a_perf_add_normalized_calculation_lookup_indexes.py`
6. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/database_models.py tests/unit/libs/portfolio-common/test_database_models.py alembic/versions/9b0c1d2e3f4a_perf_add_normalized_calculation_lookup_indexes.py`
7. `git diff --check`

Results:

1. Focused database model index proof: `5 passed`
2. Portfolio-common unit pack: `487 passed`
3. Alembic head proof: `9b0c1d2e3f4a (head)`
4. Migration contract smoke: passed
5. Touched-surface ruff: passed
6. Touched-surface format check: passed
7. Diff hygiene: passed

## Closure

Status: Hardened.

No API route shape, wiki source, or platform contract change was required. The normalized
calculation lookup predicates now have matching database index support for production-scale
calculation throughput.
