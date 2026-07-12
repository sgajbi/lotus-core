# CR-938: Operations Missing FX Query Helper Boundary

Date: 2026-06-04

## Scope

Move missing-historical-FX dependency query and row-shaping helpers out of `OperationsRepository`
without changing support endpoint contracts, SQL predicates, sample ordering, currency/security
normalization, database execution, or database schema.

## Finding

`OperationsRepository` still owned missing-historical-FX diagnostic helpers inline, including the
base transaction query, aggregate query, sample query, sample-record shaping, and summary shaping.
Those helpers are reusable query and DTO mapping policy; the repository only needs to execute the
aggregate and sample statements and return the summary.

## Action

Extracted `operations_missing_fx_queries.py` with helpers for:

- missing historical FX base transaction query construction,
- aggregate missing-count and transaction-date range selection,
- deterministic sample selection,
- sample record normalization,
- summary DTO construction.

`OperationsRepository` now delegates missing-FX diagnostic policy to the helper while preserving
database execution, query predicates, sample ordering, and support response shape.

## Result

`operations_repository.py` shrank from 2,522 SLOC to 2,456 SLOC and remains `C (0.00)` under Radon
maintainability because the active repository is still large. The new
`operations_missing_fx_queries.py` module reports `A (55.27)` under Radon maintainability, with no
B-or-worse complexity findings in the scoped repository/helper check output. Additional operations
repository helper extractions are still required to remove this active C-ranked hotspot.

## Evidence

- `python -m pytest tests\unit\services\query_service\repositories\test_operations_repository.py -q`
  => 67 passed
- `python -m ruff check src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_health_queries.py src\services\query_service\app\repositories\operations_missing_fx_queries.py tests\unit\services\query_service\repositories\test_operations_repository.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_health_queries.py src\services\query_service\app\repositories\operations_missing_fx_queries.py tests\unit\services\query_service\repositories\test_operations_repository.py`
  => 4 files already formatted
- `python -m radon raw src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_missing_fx_queries.py`
  => `operations_repository.py` 2,456 SLOC; `operations_missing_fx_queries.py` 72 SLOC
- `python -m radon mi src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_missing_fx_queries.py -s`
  => repository `C (0.00)`, helper `A (55.27)`
- `python -m radon cc src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_missing_fx_queries.py -s`
  => no B-or-worse complexity findings in the scoped repository/helper check output
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal operations repository diagnostic-query
helper extraction that preserves API contracts, SQL semantics, operator workflows, and public
documentation truth.
