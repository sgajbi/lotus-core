# CR-912: Analytics Portfolio Timeseries Orchestration Boundary

Date: 2026-06-04

## Scope

Reduce `AnalyticsTimeseriesService.get_portfolio_timeseries` orchestration complexity without
changing public service methods, repository read order, page-token validation, diagnostics,
lineage, runtime source-data metadata, or response DTOs.

## Finding

`AnalyticsTimeseriesService.get_portfolio_timeseries` was a C-ranked method mixing portfolio
lookup, request-window resolution, request-scope fingerprinting, page-token scope validation,
business-calendar reads, observation-row orchestration, latest performance horizon lookup,
portfolio data-quality diagnostics, lineage construction, page metadata, and response assembly.

## Action

Extracted focused helpers:

- `_portfolio_timeseries_scope_fingerprint`
- `_portfolio_timeseries_cursor_date`
- `_portfolio_timeseries_diagnostics`

## Result

`get_portfolio_timeseries` now reports `A (4)` instead of `C (11)` under Radon cyclomatic
complexity. The extracted portfolio-timeseries helpers report A-ranked complexity.
`analytics_timeseries_service.py` remains `C (0.00)` under Radon maintainability, and the C-hotspot
count remains 7.

## Evidence

- `python -m pytest tests\unit\services\query_service\services\test_analytics_timeseries_service.py -q`
  => 70 passed
- `python -m ruff format src\services\query_service\app\services\analytics_timeseries_service.py`
  => formatted
- `python -m radon cc src\services\query_service\app\services\analytics_timeseries_service.py -s`
  => `get_portfolio_timeseries - A (4)`; extracted portfolio-timeseries helpers A-ranked
- `python -m radon mi src -s | Select-String " - C| - D| - E| - F"`
  => 7 C-ranked maintainability hotspots

## Wiki Decision

No wiki source update is required. This is an internal service-orchestration boundary refactor that
preserves API contracts, supported features, operator workflows, and public documentation truth.
