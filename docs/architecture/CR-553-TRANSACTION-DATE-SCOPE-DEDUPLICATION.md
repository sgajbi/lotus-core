# CR-553: Transaction Date Scope Deduplication

Date: 2026-05-31

## Scope

Query-service operations support repository latest transaction date reads.

## Finding

`OperationsRepository.get_latest_transaction_date(...)` and
`get_latest_transaction_date_as_of(...)` repeated the same support-read transaction date scope:
portfolio filtering, maximum transaction-date projection, and optional durable `created_at`
snapshot fence. The booked/as-of variant adds only the business-date upper bound.

These helpers feed timestamped support overview evidence, so keeping the durable snapshot fence in
two separate statements increases the risk that latest and booked transaction-date evidence drift
apart.

## Change

1. Added `_latest_transaction_date_stmt(...)` to build the shared transaction-date support query.
2. Reused it from both latest transaction date helpers.
3. Preserved the portfolio predicate, optional business-date upper bound, durable `created_at`
   timestamp fence, scalar execution shape, datetime-to-date conversion, and response types.

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
is a maintainability hardening slice that keeps latest and booked transaction-date support evidence
aligned to one governed transaction-date query scope.
