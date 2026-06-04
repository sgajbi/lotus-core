# CR-922: Analytics FX Rate Policy Boundary

Date: 2026-06-04

## Scope

Move analytics FX map retrieval and rate lookup policy out of `AnalyticsTimeseriesService` without
changing same-currency behavior, sequential cross-currency reads, missing-rate error mapping, API
contracts, or database schema.

## Finding

`AnalyticsTimeseriesService` still owned portfolio-to-reporting FX map retrieval,
position-to-portfolio FX map retrieval, same-currency identity handling, and missing-rate
classification inline. Those policies are reusable analytics infrastructure and should be isolated
from timeseries orchestration.

## Action

Extracted `analytics_fx_rates.py` with helpers for:

- fetching portfolio-to-reporting FX maps while skipping same-currency lookups,
- fetching deduplicated position-to-portfolio FX maps in deterministic currency order,
- returning identity rates for same-currency valuation rows,
- classifying missing position-to-portfolio and portfolio-to-reporting rates.

The service keeps thin wrappers so existing orchestration and tests retain the same service seam
while missing-rate helper errors still map to `AnalyticsInputError("INSUFFICIENT_DATA", ...)`.

## Result

`analytics_timeseries_service.py` shrank from 1,590 SLOC after CR-921 to 1,582 SLOC after CR-922.
The new `analytics_fx_rates.py` module reports `A (51.85)` under Radon maintainability, and all FX
helper functions report A-ranked cyclomatic complexity. `analytics_timeseries_service.py` remains
`C (0.00)` under Radon maintainability, and the C-hotspot count remains 7.

## Evidence

- `python -m pytest tests/unit/services/query_service/services/test_analytics_fx_rates.py tests/unit/services/query_service/services/test_analytics_cash_flows.py tests/unit/services/query_service/services/test_analytics_windows.py tests/unit/services/query_service/services/test_analytics_page_tokens.py tests/unit/services/query_service/services/test_analytics_export_jobs.py tests/unit/services/query_service/services/test_analytics_export_ndjson.py tests/unit/services/query_service/services/test_analytics_timeseries_service.py -q`
  => 95 passed
- `python -m ruff check src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_fx_rates.py tests\unit\services\query_service\services\test_analytics_fx_rates.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_fx_rates.py tests\unit\services\query_service\services\test_analytics_fx_rates.py`
  => 3 files already formatted
- `python -m radon raw src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_fx_rates.py`
  => `analytics_timeseries_service.py` 1,582 SLOC; `analytics_fx_rates.py` 79 SLOC
- `python -m radon mi src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_fx_rates.py -s`
  => service `C (0.00)`, helper `A (51.85)`
- `python -m radon cc src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_fx_rates.py -s`
  => service wrappers and FX helper functions A-ranked

## Wiki Decision

No wiki source update is required. This is an internal analytics FX policy refactor that preserves
API contracts, missing-FX behavior, currency conversion semantics, pagination, operator workflows,
and public documentation truth.
