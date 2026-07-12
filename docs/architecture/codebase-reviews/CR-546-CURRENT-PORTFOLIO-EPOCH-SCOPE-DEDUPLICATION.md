# CR-546: Current Portfolio Epoch Scope Deduplication

Date: 2026-05-31

## Scope

Query-service operations support repository current portfolio epoch read.

## Finding

`OperationsRepository.get_current_portfolio_epoch(...)` manually applied the same position-state
portfolio and as-of scope already centralized for reprocessing key support reads. That kept the
current epoch support read exposed to predicate drift from reprocessing key, lineage, and health
reads that use the governed position-state evidence boundary.

The current epoch query intentionally needs only the portfolio/as-of base scope because it returns
the maximum recorded position-state epoch for the portfolio at the requested observation time.

## Change

1. Reused `_apply_reprocessing_key_scope(...)` for the current portfolio epoch query.
2. Passed only `portfolio_id` and `as_of` so status, security, and watermark filters remain absent.
3. Preserved the `max(PositionState.epoch)` projection, scalar execution shape, and response type.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
5. `python -m ruff format --check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
6. `git diff --check`

Results:

1. Focused operations repository proof passed.
2. Alembic reported a single current head.
3. Migration SQL contract smoke passed.
4. Touched-surface ruff passed.
5. Touched-surface format check passed.
6. Whitespace check passed.

## Closure

Status: Hardened.

No database migration, API route shape, wiki source, or platform contract change was required. This
is a maintainability hardening slice that keeps the current portfolio epoch support read aligned
with the governed position-state scope used by reprocessing support evidence.
