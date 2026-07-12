# CR-541: Load Run Job Scope Deduplication

Date: 2026-05-31

## Scope

Query-service operations support repository load-run progress job reads.

## Finding

`OperationsRepository.get_load_run_progress(...)` maintained the same load-run job scope across
valuation and aggregation support subqueries:

1. load-run portfolio id prefix,
2. optional as-of `updated_at` guard.

That scope was repeated in valuation summary, aggregation summary, and valuation-to-position
timeseries handoff statements. The valuation-specific actionable and superseded-epoch predicates
were correct, but the shared load-run job scope itself was still drift-prone.

## Change

1. Added `_apply_load_run_job_scope(...)` for shared load-run job predicates.
2. Reused it for valuation summary, aggregation summary, and valuation handoff subqueries.
3. Preserved existing valuation actionable-job filtering, completed-handoff filtering,
   superseded-epoch exclusion, aggregation job filtering, as-of semantics, execution order, and
   response shape.

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
is a maintainability hardening slice that keeps load-run valuation and aggregation support job
reads aligned to one governed job scope.
