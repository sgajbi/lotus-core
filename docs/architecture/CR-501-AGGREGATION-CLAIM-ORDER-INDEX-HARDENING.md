# CR-501: Aggregation Claim Order Index Hardening

Date: 2026-05-28

## Scope

Portfolio aggregation worker claim ordering for `portfolio_aggregation_jobs`.

## Finding

The portfolio time-series aggregation worker claims pending jobs through a
`SELECT ... FOR UPDATE SKIP LOCKED` eligibility query filtered by `status = 'PENDING'` and ordered
by portfolio and aggregation date. Existing indexes covered adjacent operations views, but none
matched the full worker claim shape of status plus portfolio/date ordering.

The eligibility query also did not include a unique tie-breaker in SQL order, and the subsequent
`UPDATE ... RETURNING` result was returned without re-sorting. Under concurrent workers or same-day
jobs, that left claim-result order dependent on database return behavior rather than an explicit
contract.

## Change

Added SQLAlchemy model index and Alembic migration
`c0d7e8f9a0b1_perf_add_aggregation_claim_order_index.py`:

1. `ix_portfolio_aggregation_jobs_claim_order` on
   `portfolio_aggregation_jobs(status, portfolio_id, aggregation_date, id)`.

Updated the aggregation claim query to order by portfolio, aggregation date, and id. The repository
now sorts claimed jobs by the same tuple after `UPDATE ... RETURNING`, preserving deterministic
worker processing order independent of database return ordering.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/portfolio_aggregation_service/repositories/test_timeseries_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py src/libs/portfolio-common/portfolio_common/timeseries_repository_base.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/portfolio_aggregation_service/repositories/test_timeseries_repository.py alembic/versions/c0d7e8f9a0b1_perf_add_aggregation_claim_order_index.py`
5. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/database_models.py src/libs/portfolio-common/portfolio_common/timeseries_repository_base.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/portfolio_aggregation_service/repositories/test_timeseries_repository.py alembic/versions/c0d7e8f9a0b1_perf_add_aggregation_claim_order_index.py`
6. `git diff --check`

Results:

1. Focused model and aggregation repository proof: `16 passed`
2. Alembic head proof: `c0d7e8f9a0b1 (head)`
3. Migration contract smoke: passed
4. Touched-surface ruff: passed
5. Touched-surface format check: passed
6. Whitespace check: passed

## Closure

Status: Hardened.

No API route shape, wiki source, or platform contract change was required. The aggregation worker
claim path now has an index and deterministic ordering aligned to its concurrency contract.
