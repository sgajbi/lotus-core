# CR-503: Position State Scheduler Index Hardening

Date: 2026-05-29

## Scope

Valuation scheduler scans over `position_state`.

## Finding

The valuation scheduler repeatedly scans `position_state` for lagging keys, terminal reprocessing
keys, and backfill candidates. These paths filter by `watermark_date` or `status` and process
bounded batches in oldest-`updated_at` order.

Existing indexes led with `watermark_date`, which helps date filtering but does not directly support
the scheduler's oldest-updated-first batch order. The SQL ordering also lacked a deterministic key
tie-breaker for rows sharing the same `updated_at`.

## Change

Added SQLAlchemy model indexes and Alembic migration
`c0d9e0f1a2b3_perf_add_position_state_scheduler_indexes.py`:

1. `ix_position_state_updated_watermark_key` on
   `position_state(updated_at, watermark_date, portfolio_id, security_id)`.
2. `ix_position_state_status_updated_watermark_key` on
   `position_state(status, updated_at, watermark_date, portfolio_id, security_id)`.

Updated the valuation repository scheduler scans to order by `updated_at`, `portfolio_id`, and
`security_id`, preserving oldest-updated-first scheduling while making pagination deterministic.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/calculators/position_valuation_calculator/repositories/test_valuation_repository_worker_metrics.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py src/libs/portfolio-common/portfolio_common/valuation_repository_base.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/calculators/position_valuation_calculator/repositories/test_valuation_repository_worker_metrics.py alembic/versions/c0d9e0f1a2b3_perf_add_position_state_scheduler_indexes.py`
5. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/database_models.py src/libs/portfolio-common/portfolio_common/valuation_repository_base.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/calculators/position_valuation_calculator/repositories/test_valuation_repository_worker_metrics.py alembic/versions/c0d9e0f1a2b3_perf_add_position_state_scheduler_indexes.py`
6. `git diff --check`

Results:

1. Focused model and valuation repository proof: `25 passed`
2. Alembic head proof: `c0d9e0f1a2b3 (head)`
3. Migration contract smoke: passed
4. Touched-surface ruff: passed
5. Touched-surface format check: passed
6. Whitespace check: passed

## Closure

Status: Hardened.

No API route shape, wiki source, or platform contract change was required. The valuation scheduler
now has index support and deterministic ordering aligned to its bounded batch scan semantics.
