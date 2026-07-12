# CR-492: Transaction Date Range Predicate Hardening

Date: 2026-05-28

## Scope

Transaction-date predicates in query-service, position-calculator, and financial-reconciliation
repositories.

## Finding

Several hot reads wrapped `transactions.transaction_date` in `date(...)` for filtering. That keeps
business-date semantics readable, but it makes the database evaluate a function over the column and
prevents ordinary `transaction_date` B-tree indexes from being used as clean range predicates.

Reviewed paths:

1. projected settlement cashflow series,
2. projected cashflow evidence timestamps,
3. operations latest transaction date and as-of latest transaction date,
4. operations missing historical FX dependency scan,
5. position calculator transaction replay windows,
6. financial reconciliation transaction/cashflow source rows.

## Change

Replaced function-wrapped transaction-date filters with raw timestamp range predicates:

1. before-start checks now use `transactions.transaction_date < <start-of-business-day>`,
2. on-or-after checks now use `transactions.transaction_date >= <start-of-business-day>`,
3. as-of business-date checks now use `transactions.transaction_date < <start-of-next-day>`,
4. single business-date equality checks now use `[start-of-day, start-of-next-day)`.

Where a method returns a `date`, the repository now selects the latest timestamp and converts it to
`date` in Python, preserving the public return contract while keeping SQL index-friendly.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_query_cashflow_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/calculators/position_calculator/repositories/test_position_repository.py tests/unit/services/financial_reconciliation_service/test_reconciliation_repository.py -q`
2. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
3. `python -m ruff check src/services/query_service/app/repositories/cashflow_repository.py src/services/query_service/app/repositories/operations_repository.py src/services/calculators/position_calculator/app/repositories/position_repository.py src/services/financial_reconciliation_service/app/repositories/reconciliation_repository.py tests/unit/services/query_service/repositories/test_query_cashflow_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/calculators/position_calculator/repositories/test_position_repository.py tests/unit/services/financial_reconciliation_service/test_reconciliation_repository.py`
4. `python -m ruff format --check src/services/query_service/app/repositories/cashflow_repository.py src/services/query_service/app/repositories/operations_repository.py src/services/calculators/position_calculator/app/repositories/position_repository.py src/services/financial_reconciliation_service/app/repositories/reconciliation_repository.py tests/unit/services/query_service/repositories/test_query_cashflow_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/calculators/position_calculator/repositories/test_position_repository.py tests/unit/services/financial_reconciliation_service/test_reconciliation_repository.py`

Results:

1. Focused cross-repository proof: `89 passed`
2. Operations repository proof: `67 passed`
3. Touched-surface ruff: passed
4. Touched-surface format check: passed

## Closure

Status: Hardened.

No API route shape, database migration, wiki source, or platform contract change was required. The
affected reads now preserve business-date behavior while allowing transaction-date indexes from
CR-490 and earlier migrations to support filtering directly.
