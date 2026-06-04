# CR-908: Analytics Portfolio Observation Boundary

Date: 2026-06-04

## Scope

Reduce `AnalyticsTimeseriesService` portfolio-observation complexity without changing public
service methods, snapshot epoch selection, observation date paging, FX lookup behavior,
portfolio/position cash-flow handling, previous-EOD continuity repair, quality distribution,
next-page token semantics, or response DTOs.

## Finding

`AnalyticsTimeseriesService._portfolio_observation_rows` was a D-ranked method mixing snapshot
epoch reads, observed-date paging, position row reads, FX support reads, portfolio and position
cash-flow reads, previous-EOD continuity state, per-date observation assembly, FX guard behavior,
quality classification, and next-page token construction.

## Action

Extracted focused helpers:

- `_PortfolioObservationPageScope`
- `_PortfolioObservationSupportInputs`
- `_portfolio_observation_page_scope`
- `_portfolio_observation_support_inputs`
- `_portfolio_position_currencies`
- `_portfolio_position_security_ids`
- `_previous_eod_by_security`
- `_portfolio_observations_for_page`
- `_portfolio_row_buckets`
- `_portfolio_observation_for_date`
- `_portfolio_to_reporting_observation_rate`
- `_position_to_portfolio_observation_rate`
- `_portfolio_observation_next_page_token`

## Result

`_portfolio_observation_rows` now reports `A (2)` instead of `D (22)` under Radon cyclomatic
complexity. The extracted portfolio-observation helpers report A-ranked complexity.
`analytics_timeseries_service.py` remains `C (0.00)` under Radon maintainability, and the C-hotspot
count remains 7.

## Evidence

- `python -m pytest tests\unit\services\query_service\services\test_analytics_timeseries_service.py -q`
  => 70 passed
- `python -m ruff format src\services\query_service\app\services\analytics_timeseries_service.py`
  => formatted
- `python -m radon cc src\services\query_service\app\services\analytics_timeseries_service.py -s`
  => `_portfolio_observation_rows - A (2)`; extracted portfolio-observation helpers A-ranked
- `python -m radon mi src -s | Select-String " - C| - D| - E| - F"`
  => 7 C-ranked maintainability hotspots

## Wiki Decision

No wiki source update is required. This is an internal service-helper boundary refactor that
preserves API contracts, supported features, operator workflows, and public documentation truth.
