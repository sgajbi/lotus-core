# CR-941: Operations Load-Run Query Helper Boundary

Date: 2026-06-04

## Scope

Move load-run progress statement construction and summary shaping out of `OperationsRepository`
without changing support endpoint contracts, load-run progress figures, valuation handoff latency
calculation, stale/superseded valuation semantics, database execution, or database schema.

## Finding

`OperationsRepository` still owned load-run progress scalar statement construction, valuation and
aggregation summary statement construction, valuation-to-position-timeseries handoff diagnostics,
and `LoadRunProgressSummary` row shaping inline. That made the repository responsible for both
database execution and a large amount of load-run support-query policy.

## Action

Extracted `operations_load_run_queries.py` with helpers for:

- load-run progress scalar statements,
- valuation and aggregation summary statements,
- valuation-to-position-timeseries handoff latency and missing-timeseries diagnostics,
- `LoadRunProgressSummary` construction from executed rows.

`OperationsRepository` now keeps the repository-owned valuation actionability and superseded-epoch
predicates, passes those SQL expressions into the helper, executes the returned statements, and
returns the helper-shaped support DTO.

## Result

`operations_repository.py` shrank from 2,211 SLOC to 1,832 SLOC and remains `C (0.00)` under Radon
maintainability because the active repository is still large. The new
`operations_load_run_queries.py` module reports `A (44.96)` under Radon maintainability, with no
B-or-worse complexity findings in the scoped repository/helper check output. Additional operations
repository extractions are still required to remove this active C-ranked hotspot.

## Evidence

- `python -m pytest tests\unit\services\query_service\repositories\test_operations_repository.py -q`
  => 67 passed
- `python -m ruff check src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_load_run_queries.py tests\unit\services\query_service\repositories\test_operations_repository.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_load_run_queries.py tests\unit\services\query_service\repositories\test_operations_repository.py`
  => 3 files already formatted
- `make monetary-float-guard`
  => passed
- `python -m radon raw src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_load_run_queries.py`
  => `operations_repository.py` 1,832 SLOC; `operations_load_run_queries.py` 400 SLOC
- `python -m radon mi src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_load_run_queries.py -s`
  => repository `C (0.00)`, helper `A (44.96)`
- `python -m radon cc src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_load_run_queries.py -s`
  => no B-or-worse complexity findings in the scoped repository/helper check output

## Wiki Decision

No wiki source update is required. This is an internal operations repository load-run support-query
helper extraction that preserves API contracts, SQL semantics, operator workflows, and public
documentation truth.
