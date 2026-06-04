# CR-899: Position Timeseries Row Assembly Boundary

Date: 2026-06-04

## Scope

Reduce `AnalyticsTimeseriesService.get_position_timeseries` complexity without changing public
service methods, repository call semantics, paging tokens, FX behavior, cash-flow semantics, or
response DTOs.

## Finding

`AnalyticsTimeseriesService.get_position_timeseries` was an E-ranked method mixing request-scope
fingerprinting, page-token validation, snapshot-epoch resolution, page reads, support-data reads,
cash-flow grouping, FX map lookup, continuity repair, position row assembly, quality distribution,
next-page token construction, and response metadata assembly.

The method sits inside `analytics_timeseries_service.py`, which remains a C-ranked maintainability
hotspot. The immediate risk was that a single high-complexity method was responsible for both
orchestration and detailed row assembly policy.

## Action

Extracted focused private helpers inside `analytics_timeseries_service.py`:

- `_position_page_support_inputs(...)` reads page-scoped support data.
- `_position_page_scope(...)` resolves page dates and normalized security identifiers.
- `_position_page_cash_flows_by_key(...)` reads optional position cash-flow evidence.
- `_previous_position_eod_by_security(...)` resolves continuity inputs from previous rows.
- `_position_response_rows(...)` coordinates row assembly and quality distribution.
- `_position_response_row(...)` builds one response row.
- `_position_to_portfolio_rate(...)` and `_portfolio_to_reporting_rate(...)` isolate FX-rate
  failure behavior.

`get_position_timeseries` now remains responsible for request validation, snapshot/page orchestration,
next-page token generation, diagnostics, and response construction.

## Result

`AnalyticsTimeseriesService.get_position_timeseries` now reports `C (15)` instead of `E (37)` under
Radon cyclomatic complexity. The extracted row-assembly helpers all report A-ranked complexity.

`analytics_timeseries_service.py` still reports `C (0.00)` under Radon maintainability, and the
source C-hotspot count remains 7. This is a material complexity reduction, not final closure for
the analytics timeseries service.

## Evidence

Validation commands:

- `python -m pytest tests\unit\services\query_service\services\test_analytics_timeseries_service.py -q`
  => `70 passed`
- `python -m ruff check src\services\query_service\app\services\analytics_timeseries_service.py`
- `python -m ruff format src\services\query_service\app\services\analytics_timeseries_service.py`
- `python -m radon cc src\services\query_service\app\services\analytics_timeseries_service.py -s`
- `python -m radon mi src\services\query_service\app\services\analytics_timeseries_service.py -s`
- `python -m radon mi src -s | Select-String " - C| - D| - E| - F"`

No integration selection was run for this slice. The change is an internal service-helper
extraction covered by focused analytics timeseries unit tests.

## Wiki Decision

No wiki source update is required. This is an internal service-helper refactor and does not change
an operator-facing contract, API contract, or runbook.
