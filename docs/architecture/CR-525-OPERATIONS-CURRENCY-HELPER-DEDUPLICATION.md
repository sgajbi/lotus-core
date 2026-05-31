# CR-525: Operations Currency Helper Deduplication

Date: 2026-05-31

## Scope

Query-service operations support reads for missing historical FX dependency evidence.

## Finding

`OperationsRepository` carried a private `_currency_code_expr(...)` helper that duplicated the
shared query-service currency SQL helper used by FX, reporting, transaction, reference, and
analytics repositories. The duplicated helper emitted the same `upper(trim(...))` SQL shape needed
for the existing normalized FX expression-index contract, but left operations support reads with a
local copy of normalization behavior.

## Change

1. Replaced the private operations helper with `currency_code_sql_expr(...)` from
   `query_service.app.repositories.currency_codes`.
2. Removed the duplicate private helper from `OperationsRepository`.
3. Preserved the existing missing-historical-FX query shape and response behavior.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
3. `python -m ruff format --check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
4. `git diff --check`

Results:

1. Focused operations repository proof passed.
2. Touched-surface ruff passed.
3. Touched-surface format check passed.
4. Whitespace check passed.

## Closure

Status: Hardened.

No database migration, API route shape, wiki source, or platform contract change was required. This
is a repository-boundary cleanup that keeps currency normalization centralized while preserving the
existing normalized SQL predicate contract.
