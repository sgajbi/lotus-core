# CR-920: Analytics Window Policy Boundary

Date: 2026-06-04

## Scope

Move analytics window and period-start policy out of `AnalyticsTimeseriesService` without changing
explicit-window bounding, inception-date clamping, supported period semantics, invalid-window error
mapping, API contracts, or database schema.

## Finding

`AnalyticsTimeseriesService` still owned explicit window bounding, period start lookup, inception
clamping, and unsupported-period classification inline. That calendar/window policy is stable
domain behavior and should be isolated from timeseries orchestration.

## Action

Extracted `analytics_windows.py` with helpers for:

- resolving explicit versus period-driven analytics windows,
- bounding explicit end dates to the request as-of date,
- rejecting inverted explicit windows,
- calculating supported period start dates,
- clamping period starts to portfolio inception,
- classifying invalid window/period requests for service-level error mapping.

The service keeps a thin `_resolve_window` wrapper so existing orchestration and tests continue to
use the same service boundary while invalid requests still map to `AnalyticsInputError`.

## Result

`analytics_timeseries_service.py` shrank from 1,751 SLOC after CR-919 to 1,707 SLOC after CR-920.
The new `analytics_windows.py` module reports `A (54.96)` under Radon maintainability, and all
window helper functions report A-ranked cyclomatic complexity. `analytics_timeseries_service.py`
remains `C (0.00)` under Radon maintainability, and the C-hotspot count remains 7.

## Evidence

- `python -m pytest tests/unit/services/query_service/services/test_analytics_windows.py tests/unit/services/query_service/services/test_analytics_page_tokens.py tests/unit/services/query_service/services/test_analytics_export_jobs.py tests/unit/services/query_service/services/test_analytics_export_ndjson.py tests/unit/services/query_service/services/test_analytics_timeseries_service.py -q`
  => 86 passed
- `python -m ruff check src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_windows.py tests\unit\services\query_service\services\test_analytics_windows.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_windows.py tests\unit\services\query_service\services\test_analytics_windows.py`
  => 3 files already formatted
- `python -m radon raw src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_windows.py`
  => `analytics_timeseries_service.py` 1,707 SLOC; `analytics_windows.py` 61 SLOC
- `python -m radon mi src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_windows.py -s`
  => service `C (0.00)`, helper `A (54.96)`
- `python -m radon cc src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_windows.py -s`
  => window service wrapper and helper functions A-ranked

## Wiki Decision

No wiki source update is required. This is an internal analytics window policy refactor that
preserves API contracts, supported periods, pagination behavior, operator workflows, and public
documentation truth.
