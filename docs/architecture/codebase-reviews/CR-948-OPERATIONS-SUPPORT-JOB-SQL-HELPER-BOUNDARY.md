# CR-948: Operations Support Job SQL Helper Boundary

Date: 2026-06-05

## Scope

Move valuation/support-job SQL policy helpers out of `OperationsRepository` without changing
support endpoint contracts, valuation actionability semantics, superseding-epoch detection,
lineage latest-job lateral selection, stale-job priority ordering, database execution, pagination,
or database schema.

## Finding

`OperationsRepository` still owned static SQL helper policy for normalized security-id
expressions, actionable valuation-job filtering, superseding valuation-epoch checks,
latest-valuation-job lateral selection, and support-job priority ordering. Those helpers are
shared support-query policy and fit the existing `operations_support_job_queries.py` and
`operations_position_scope_queries.py` helper boundary better than the repository class.

## Action

Extended `operations_support_job_queries.py` with helpers for:

- actionable valuation-job filtering,
- superseding valuation-epoch detection,
- latest valuation-job lateral selection for lineage evidence,
- support-job stale/failed/open priority ordering.

`OperationsRepository` now imports reusable support-job and security-id expression helpers instead
of carrying private static SQL policy methods. Repository methods still own request normalization,
database execution, and response return shapes.

## Result

`operations_repository.py` shrank from 1,332 SLOC to 1,247 SLOC and improved from `C (6.24)` to
`B (9.54)` under Radon maintainability, removing it from the active source C-ranked hotspot list.
The expanded `operations_support_job_queries.py` module remains `A (35.97)` under Radon
maintainability, with no B-or-worse complexity findings in the scoped repository/helper check
output. Generated `query_service/build` copies remain separate generated-surface debt and are not
changed by this slice.

## Evidence

- `python -m pytest tests\unit\services\query_service\repositories\test_operations_repository.py -q`
  => 67 passed
- `python -m ruff check src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_support_job_queries.py tests\unit\services\query_service\repositories\test_operations_repository.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_support_job_queries.py tests\unit\services\query_service\repositories\test_operations_repository.py`
  => 3 files already formatted
- `python -m radon raw src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_support_job_queries.py`
  => `operations_repository.py` 1,247 SLOC; `operations_support_job_queries.py` 189 SLOC
- `python -m radon mi src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_support_job_queries.py -s`
  => repository `B (9.54)`, helper `A (35.97)`
- `python -m radon cc src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_support_job_queries.py -s`
  => no B-or-worse complexity findings in the scoped repository/helper check output
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed
- `python -m radon mi src -s | Select-String -Pattern " - C \("`
  => active non-generated C-ranked source hotspots now exclude `operations_repository.py`

## Wiki Decision

No wiki source update is required. This is an internal operations repository support-job SQL helper
extraction that preserves API contracts, SQL semantics, operator workflows, and public
documentation truth.
