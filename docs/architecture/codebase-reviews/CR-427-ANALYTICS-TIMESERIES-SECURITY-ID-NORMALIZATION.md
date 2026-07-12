# CR-427: Analytics Timeseries Security-ID Normalization

Date: 2026-05-28

## Scope

Query-service analytics input generation for portfolio and position timeseries.

## Finding

Analytics timeseries assembly used raw `security_id` values for prior-day ending market value
maps, position cash-flow lookup keys, position response identifiers, and several position
timeseries repository filters and joins. Whitespace drift between position, position-state,
instrument, position-history, or cashflow rows could therefore break continuity repair, miss
position-level cashflows, fragment paging keys, or exclude rows from analytics-input snapshots.

That failure mode can distort beginning market values and return inputs for downstream
performance/risk consumers even when the bank has complete position and cashflow evidence.

## Change

Reused the shared query-service security identifier normalizer in analytics timeseries service
assembly and repository query construction. Portfolio and position timeseries now normalize
security identifiers for previous-EOD maps, position cash-flow lookup maps, requested repository
security filters, position-id-derived filters, response `position_id` values, and page-token
security keys. Position timeseries repository joins and filters now compare trimmed persisted
security identifiers across position timeseries, position state, position history, instruments,
and cashflows.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_analytics_timeseries_service.py tests/unit/services/query_service/repositories/test_analytics_timeseries_repository.py -q`
2. `python -m ruff check src/services/query_service/app/repositories/analytics_timeseries_repository.py src/services/query_service/app/services/analytics_timeseries_service.py tests/unit/services/query_service/services/test_analytics_timeseries_service.py tests/unit/services/query_service/repositories/test_analytics_timeseries_repository.py`
3. `python -m pytest tests/unit/services/query_service/services -q`
4. `python -m pytest tests/unit/services/query_service/repositories -q`
5. `git diff --check`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is an
analytics-input correctness slice that prevents harmless source identifier padding from breaking
timeseries continuity and position cashflow evidence.
