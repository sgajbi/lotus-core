# CR-909: Analytics Beginning Market Value Boundary

Date: 2026-06-04

## Scope

Reduce `AnalyticsTimeseriesService` beginning-market-value policy complexity without changing public
service methods, previous-EOD continuity behavior, cash-book settlement handling, BOD position-flow
repair, new internally funded position handling, external-flow guards, or response DTOs.

## Finding

`AnalyticsTimeseriesService._effective_beginning_market_value` was a C-ranked method mixing stored
BOD value normalization, previous-EOD continuity, internal cash-book settlement handling, BOD flow
repair, no-prior-capital handling, and fallback to stored beginning value.

## Action

Extracted focused policy predicates:

- `_has_prior_eod_continuity`
- `_is_internal_cash_book_settlement`
- `_can_repair_beginning_from_previous_eod`
- `_is_new_internally_funded_position`

## Result

`_effective_beginning_market_value` now reports `A (5)` instead of `C (17)` under Radon cyclomatic
complexity. The extracted beginning-market-value policy predicates report A-ranked complexity.
`analytics_timeseries_service.py` remains `C (0.00)` under Radon maintainability, and the C-hotspot
count remains 7.

## Evidence

- `python -m pytest tests\unit\services\query_service\services\test_analytics_timeseries_service.py -q`
  => 70 passed
- `python -m ruff format src\services\query_service\app\services\analytics_timeseries_service.py`
  => formatted
- `python -m radon cc src\services\query_service\app\services\analytics_timeseries_service.py -s`
  => `_effective_beginning_market_value - A (5)`; extracted policy predicates A-ranked
- `python -m radon mi src -s | Select-String " - C| - D| - E| - F"`
  => 7 C-ranked maintainability hotspots

## Wiki Decision

No wiki source update is required. This is an internal service-helper boundary refactor that
preserves API contracts, supported features, operator workflows, and public documentation truth.
