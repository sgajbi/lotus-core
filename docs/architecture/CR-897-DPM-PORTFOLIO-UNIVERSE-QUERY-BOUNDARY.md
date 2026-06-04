# CR-897: DPM Portfolio Universe Query Boundary

Date: 2026-06-04

## Scope

Reduce `ReferenceDataRepository` DPM portfolio-universe query complexity without changing SQL
semantics, public repository methods, or API response contracts.

## Finding

`ReferenceDataRepository.list_dpm_portfolio_universe_candidates` was a B-ranked method that mixed
DPM mandate eligibility predicates, effective-date filtering, canonical mandate-binding ranking,
deterministic sort ordering, cursor pagination, limit handling, execution, and row extraction in
one repository method.

The surrounding file remains a C-ranked maintainability hotspot, so adding more local helper code
inside the same module would not move the architecture in the right direction.

## Action

Extracted focused DPM portfolio-universe query helpers into `reference_dpm_queries.py`:

- `dpm_portfolio_universe_stmt(...)` builds the DPM universe candidate query for the requested
  read scope, cursor, and limit.
- `_dpm_portfolio_universe_predicates(...)` keeps DPM source-eligibility predicates together.
- `_ranked_dpm_portfolio_universe_binding_ids(...)` owns canonical mandate-binding ranking for
  this read boundary.

`ReferenceDataRepository.list_dpm_portfolio_universe_candidates` now delegates SQL construction,
executes the query, and returns the existing scalar rows.

## Result

`list_dpm_portfolio_universe_candidates` now reports `A (1)` instead of `B (6)` under Radon
cyclomatic complexity. The extracted DPM query helpers report A-ranked complexity.

`reference_data_repository.py` improved from `C (7.55)` to `C (8.74)` under Radon maintainability.
The new `reference_dpm_queries.py` helper module reports `A (53.24)`. The source C-hotspot count
remains 8.

## Evidence

Validation commands:

- `python -m pytest tests\unit\services\query_service\repositories\test_reference_data_repository.py -q`
  => `32 passed`
- `python -m ruff check src\services\query_service\app\repositories\reference_data_repository.py src\services\query_service\app\repositories\reference_dpm_queries.py`
- `python -m ruff format src\services\query_service\app\repositories\reference_data_repository.py src\services\query_service\app\repositories\reference_dpm_queries.py`
- `python -m radon cc src\services\query_service\app\repositories\reference_data_repository.py src\services\query_service\app\repositories\reference_dpm_queries.py -s`
- `python -m radon mi src\services\query_service\app\repositories\reference_data_repository.py src\services\query_service\app\repositories\reference_dpm_queries.py -s`
- `python -m radon mi src -s | Select-String " - C| - D| - E| - F"`

No integration selection was run for this slice. The change is an internal SQL-helper extraction
covered by reference data repository SQL-shape unit tests.

## Wiki Decision

No wiki source update is required. This is an internal repository helper refactor and does not
change an operator-facing contract, API contract, or runbook.
