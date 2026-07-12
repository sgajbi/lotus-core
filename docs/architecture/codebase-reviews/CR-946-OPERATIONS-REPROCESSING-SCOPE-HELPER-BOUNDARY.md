# CR-946: Operations Reprocessing Scope Helper Boundary

Date: 2026-06-04

## Scope

Move reprocessing key and reset-watermark job scope construction out of `OperationsRepository`
without changing support endpoint contracts, reset-watermark eligibility semantics, positive
position-history scope checks, stale-key ordering, job filtering, database execution, pagination,
or database schema.

## Finding

`OperationsRepository` still owned reprocessing status normalization, stale-key priority ordering,
reset-watermark job portfolio eligibility, payload security/date expression extraction,
reprocessing-key filtering, and reprocessing-job filtering inline. Those helpers are pure
support-query policy and reset-scope construction; the repository only needs to normalize request
filters, execute statements, and return rows or DTOs.

## Action

Extracted `operations_reprocessing_queries.py` with helpers for:

- reprocessing status normalization,
- stale reprocessing-key priority ordering,
- reset-watermark portfolio eligibility checks,
- reset-watermark job payload scope construction,
- reprocessing key filtering,
- reprocessing job identity, security, and composed scope filtering.

`OperationsRepository` now delegates reprocessing key and reset-watermark job query policy to the
helper while preserving database execution, ordering, pagination, and response shape.

## Result

`operations_repository.py` shrank from 1,538 SLOC to 1,403 SLOC and improved from `C (0.21)` to
`C (4.42)` under Radon maintainability, but remains a C-ranked active hotspot. The new
`operations_reprocessing_queries.py` module reports `A (43.47)` under Radon maintainability, with
no B-or-worse complexity findings in the scoped repository/helper check output. Additional
operations repository extractions are still required to remove this active C-ranked hotspot.

## Evidence

- `python -m pytest tests\unit\services\query_service\repositories\test_operations_repository.py -q`
  => 67 passed
- `python -m ruff check src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_reprocessing_queries.py tests\unit\services\query_service\repositories\test_operations_repository.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_reprocessing_queries.py tests\unit\services\query_service\repositories\test_operations_repository.py`
  => 3 files already formatted
- `python -m radon raw src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_reprocessing_queries.py`
  => `operations_repository.py` 1,403 SLOC; `operations_reprocessing_queries.py` 138 SLOC
- `python -m radon mi src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_reprocessing_queries.py -s`
  => repository `C (4.42)`, helper `A (43.47)`
- `python -m radon cc src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_reprocessing_queries.py -s`
  => no B-or-worse complexity findings in the scoped repository/helper check output
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal operations repository reprocessing
query-scope helper extraction that preserves API contracts, SQL semantics, operator workflows, and
public documentation truth.
