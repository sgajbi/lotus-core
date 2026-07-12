# CR-896: Reference FX Rate Query Boundary

Date: 2026-06-04

## Scope

Reduce `ReferenceDataRepository` FX-rate query complexity without changing SQL semantics, public
repository methods, or API response contracts.

## Finding

`ReferenceDataRepository.list_latest_fx_rates` was a B-ranked method that mixed requested currency
pair normalization, duplicate removal, latest-rate date subquery construction, latest-rate join
construction, ordering, execution, and row extraction in one repository method.

The surrounding file remains a C-ranked maintainability hotspot, so adding more local helper code
inside the same module would not move the architecture in the right direction.

## Action

Extracted focused FX reference query helpers into `reference_fx_queries.py`:

- `normalized_currency_pairs(...)` normalizes and deduplicates requested FX pairs.
- `latest_fx_rates_stmt(...)` builds the latest-rate query for normalized pairs and an as-of date.
- `_latest_fx_rate_dates_subquery(...)` builds the grouped latest-rate-date subquery.

`ReferenceDataRepository.list_latest_fx_rates` now validates empty input, delegates normalization
and SQL construction, executes the query, and returns the existing scalar rows.

## Result

`list_latest_fx_rates` now reports `A (3)` instead of `B (6)` under Radon cyclomatic complexity.
The extracted FX query helpers report A-ranked complexity.

`reference_data_repository.py` improved from `C (6.94)` to `C (7.55)` under Radon maintainability.
The new `reference_fx_queries.py` helper module reports `A (60.98)`. The source C-hotspot count
remains 8.

## Evidence

Validation commands:

- `python -m pytest tests\unit\services\query_service\repositories\test_reference_data_repository.py -q`
  => `32 passed`
- `python -m ruff check src\services\query_service\app\repositories\reference_data_repository.py src\services\query_service\app\repositories\reference_fx_queries.py`
- `python -m radon cc src\services\query_service\app\repositories\reference_data_repository.py src\services\query_service\app\repositories\reference_fx_queries.py -s`
- `python -m radon mi src\services\query_service\app\repositories\reference_data_repository.py src\services\query_service\app\repositories\reference_fx_queries.py -s`

No integration selection was run for this slice. The change is an internal SQL-helper extraction
covered by reference data repository SQL-shape unit tests.

## Wiki Decision

No wiki source update is required. This is an internal repository helper refactor and does not
change an operator-facing contract, API contract, or runbook.
