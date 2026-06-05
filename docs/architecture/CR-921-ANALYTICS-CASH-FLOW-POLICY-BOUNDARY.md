# CR-921: Analytics Cash Flow Policy Boundary

Date: 2026-06-04

## Scope

Move analytics cash-flow observation construction, portfolio/reporting FX conversion checks,
position-flow grouping, internal/external flow predicates, and beginning-market-value repair policy
out of `AnalyticsTimeseriesService` without changing API contracts, database schema, cash-flow
classification semantics, missing-FX error mapping, or timeseries response values.

## Finding

`AnalyticsTimeseriesService` still owned cash-flow normalization and capital-continuity repair rules
inline. Those rules are stable private-banking analytics policy and should be reusable outside
timeseries orchestration.

## Action

Extracted `analytics_cash_flows.py` with helpers for:

- building `CashFlowObservation` DTOs from repository rows,
- grouping portfolio cash flows by valuation date with portfolio/reporting FX conversion,
- grouping position cash flows by normalized security/date key,
- detecting external and internal-only cash-flow sets,
- identifying cash-book positions,
- resolving effective beginning market value for prior-EOD continuity, internal cash-book
  settlement, internally funded positions, and stored beginning values.

The service keeps thin wrappers for existing orchestration and protected test seams while mapping
helper missing-FX errors back to `AnalyticsInputError("INSUFFICIENT_DATA", ...)`.

## Result

`analytics_timeseries_service.py` shrank from 1,707 SLOC after CR-920 to 1,590 SLOC after CR-921.
The new `analytics_cash_flows.py` module reports `A (37.12)` under Radon maintainability, and all
cash-flow helper functions report A-ranked cyclomatic complexity. `analytics_timeseries_service.py`
remains `C (0.00)` under Radon maintainability, and the C-hotspot count remains 7.

## Evidence

- `python -m pytest tests/unit/services/query_service/services/test_analytics_cash_flows.py tests/unit/services/query_service/services/test_analytics_windows.py tests/unit/services/query_service/services/test_analytics_page_tokens.py tests/unit/services/query_service/services/test_analytics_export_jobs.py tests/unit/services/query_service/services/test_analytics_export_ndjson.py tests/unit/services/query_service/services/test_analytics_timeseries_service.py -q`
  => 91 passed
- `python -m ruff check src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_cash_flows.py tests\unit\services\query_service\services\test_analytics_cash_flows.py`
  => all checks passed
- `python -m ruff format src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_cash_flows.py tests\unit\services\query_service\services\test_analytics_cash_flows.py`
  => files formatted
- `python -m radon raw src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_cash_flows.py`
  => `analytics_timeseries_service.py` 1,590 SLOC; `analytics_cash_flows.py` 169 SLOC
- `python -m radon mi src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_cash_flows.py -s`
  => service `C (0.00)`, helper `A (37.12)`
- `python -m radon cc src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_cash_flows.py -s`
  => service wrappers and cash-flow helper functions A-ranked

## Wiki Decision

No wiki source update is required. This is an internal analytics cash-flow policy refactor that
preserves API contracts, cash-flow semantics, missing-FX behavior, supported periods, pagination,
operator workflows, and public documentation truth.
