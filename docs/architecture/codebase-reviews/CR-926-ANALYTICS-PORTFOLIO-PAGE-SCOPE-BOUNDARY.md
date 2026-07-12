# CR-926: Analytics Portfolio Page Scope Boundary

Date: 2026-06-04

## Scope

Move portfolio-timeseries page-scope derivation, position-row bucketing, observation FX-rate lookup,
and portfolio next-page token payload construction out of `AnalyticsTimeseriesService` without
changing paging behavior, missing-FX behavior, token semantics, API contracts, or database schema.

## Finding

`AnalyticsTimeseriesService` still owned portfolio observation page slicing, page-date row buckets,
same-currency observation rates, missing cross-currency rate classification, and portfolio
next-page token payloads inline. Those policies are reusable portfolio page support behavior and
should be isolated from timeseries orchestration.

## Action

Extracted `analytics_portfolio_pages.py` with helpers for:

- applying portfolio cursor dates and page-size limits,
- determining whether another page exists,
- bucketing position rows by requested page date,
- resolving portfolio-to-reporting observation FX rates,
- resolving position-to-portfolio observation FX rates,
- constructing portfolio next-page token payloads.

The service keeps thin wrappers so existing orchestration and protected tests retain the same
service seam while missing-rate helper errors still map to `AnalyticsInputError("INSUFFICIENT_DATA",
...)`.

## Result

`analytics_timeseries_service.py` shrank from 1,523 SLOC after CR-925 to 1,513 SLOC after CR-926.
Its Radon maintainability score improved from `C (0.00)` to `C (1.52)`. The new
`analytics_portfolio_pages.py` module reports `A (46.28)` under Radon maintainability, and all
portfolio-page helper functions report A-ranked cyclomatic complexity. The C-hotspot count remains
7.

## Evidence

- `python -m pytest tests/unit/services/query_service/services/test_analytics_portfolio_pages.py tests/unit/services/query_service/services/test_analytics_position_pages.py tests/unit/services/query_service/services/test_analytics_quality.py tests/unit/services/query_service/services/test_analytics_pagination.py tests/unit/services/query_service/services/test_analytics_fx_rates.py tests/unit/services/query_service/services/test_analytics_cash_flows.py tests/unit/services/query_service/services/test_analytics_windows.py tests/unit/services/query_service/services/test_analytics_page_tokens.py tests/unit/services/query_service/services/test_analytics_export_jobs.py tests/unit/services/query_service/services/test_analytics_export_ndjson.py tests/unit/services/query_service/services/test_analytics_timeseries_service.py -q`
  => 113 passed
- `python -m ruff check src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_portfolio_pages.py tests\unit\services\query_service\services\test_analytics_portfolio_pages.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_portfolio_pages.py tests\unit\services\query_service\services\test_analytics_portfolio_pages.py`
  => 3 files already formatted
- `python -m radon raw src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_portfolio_pages.py`
  => `analytics_timeseries_service.py` 1,513 SLOC; `analytics_portfolio_pages.py` 85 SLOC
- `python -m radon mi src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_portfolio_pages.py -s`
  => service `C (1.52)`, helper `A (46.28)`
- `python -m radon cc src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_portfolio_pages.py -s`
  => service wrappers and portfolio-page helper functions A-ranked

## Wiki Decision

No wiki source update is required. This is an internal analytics portfolio-page refactor that
preserves API contracts, page-token semantics, missing-FX behavior, operator workflows, and public
documentation truth.
