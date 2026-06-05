# CR-936: Reference Data Query Helper Boundary

Date: 2026-06-04

## Scope

Move reusable reference-data SQL helper construction out of `ReferenceDataRepository` without
changing repository method signatures, SQL predicates, ranked latest-effective selection semantics,
market/reference API contracts, metrics, or database schema.

## Finding

`ReferenceDataRepository` still owned reusable SQL construction helpers inline, including
effective-window predicates, reference-status normalization, canonical series ranking,
latest-effective row ranking, DPM mandate ranking, model-target ranking, and instrument-eligibility
ranking. Those helpers are pure query-building policy and do not need repository instance state.

## Action

Extracted `reference_data_query_helpers.py` with helpers for:

- effective-window filtering,
- reference status normalization,
- canonical quality-preferred series ranking,
- latest effective row ranking,
- DPM mandate binding ranking,
- model portfolio target ranking,
- instrument eligibility ranking.

`ReferenceDataRepository` now imports those helpers while preserving its repository orchestration,
database execution, ordering, and return-shape behavior.

## Result

`reference_data_repository.py` shrank from 1,278 SLOC to 1,163 SLOC and improved from `C (8.74)`
to `B (9.24)` under Radon maintainability. The new `reference_data_query_helpers.py` module
reports `A (61.46)` under Radon maintainability, with no B-or-worse complexity findings in the
scoped repository/helper check output. This removes the active query-service reference-data
repository from the C-ranked maintainability hotspot list; the generated `query_service/build` copy
remains separate generated-surface debt.

## Evidence

- `python -m pytest tests\unit\services\query_service\repositories\test_reference_data_repository.py -q`
  => 32 passed
- `python -m ruff check src\services\query_service\app\repositories\reference_data_repository.py src\services\query_service\app\repositories\reference_data_query_helpers.py tests\unit\services\query_service\repositories\test_reference_data_repository.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\repositories\reference_data_repository.py src\services\query_service\app\repositories\reference_data_query_helpers.py tests\unit\services\query_service\repositories\test_reference_data_repository.py`
  => 3 files already formatted
- `python -m radon raw src\services\query_service\app\repositories\reference_data_repository.py src\services\query_service\app\repositories\reference_data_query_helpers.py`
  => `reference_data_repository.py` 1,163 SLOC; `reference_data_query_helpers.py` 132 SLOC
- `python -m radon mi src\services\query_service\app\repositories\reference_data_repository.py src\services\query_service\app\repositories\reference_data_query_helpers.py -s`
  => repository `B (9.24)`, helper `A (61.46)`
- `python -m radon cc src\services\query_service\app\repositories\reference_data_repository.py src\services\query_service\app\repositories\reference_data_query_helpers.py -s`
  => no B-or-worse complexity findings in the scoped repository/helper check output
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal repository query-helper extraction that
preserves API contracts, SQL semantics, operator workflows, and public documentation truth.
