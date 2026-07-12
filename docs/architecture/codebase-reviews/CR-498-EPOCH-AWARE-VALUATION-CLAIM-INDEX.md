# CR-498: Epoch-Aware Valuation Claim Index

Date: 2026-05-28

## Scope

Valuation-worker claim ordering for `portfolio_valuation_jobs`.

## Finding

The valuation worker claims pending jobs through a `SELECT ... FOR UPDATE SKIP LOCKED` subquery
ordered by portfolio, security, valuation date, and `epoch DESC`, while excluding jobs superseded by
newer epochs. The legacy live index `idx_portfolio_valuation_jobs_claim_order` covered status,
portfolio, security, valuation date, and id, but omitted epoch. That meant the index shape did not
fully match the worker's newest-epoch-first ordering.

The legacy index also was not declared in SQLAlchemy model metadata, so fresh schema metadata did not
fully describe the migration-backed worker path.

## Change

Added SQLAlchemy model index and Alembic migration
`c0d5e6f7a8b9_perf_add_epoch_aware_valuation_claim_index.py`:

1. drops legacy `idx_portfolio_valuation_jobs_claim_order`,
2. creates `ix_portfolio_valuation_jobs_claim_order_epoch` on
   `portfolio_valuation_jobs(status, portfolio_id, security_id, valuation_date, epoch DESC, id)`.

Added model index proof and repository query-shape proof that the claim subquery preserves
`epoch DESC` in the ordering that the index supports.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/calculators/position_valuation_calculator/repositories/test_valuation_repository_worker_metrics.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/calculators/position_valuation_calculator/repositories/test_valuation_repository_worker_metrics.py alembic/versions/c0d5e6f7a8b9_perf_add_epoch_aware_valuation_claim_index.py`
5. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/database_models.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/calculators/position_valuation_calculator/repositories/test_valuation_repository_worker_metrics.py alembic/versions/c0d5e6f7a8b9_perf_add_epoch_aware_valuation_claim_index.py`

Results:

1. Focused model and valuation repository proof: `22 passed`
2. Alembic head proof: `c0d5e6f7a8b9 (head)`
3. Migration contract smoke: passed
4. Touched-surface ruff: passed
5. Touched-surface format check: passed

## Closure

Status: Hardened.

No API route shape, wiki source, or platform contract change was required. The valuation worker
claim path now has a single epoch-aware index aligned to the actual filter and ordering semantics.
