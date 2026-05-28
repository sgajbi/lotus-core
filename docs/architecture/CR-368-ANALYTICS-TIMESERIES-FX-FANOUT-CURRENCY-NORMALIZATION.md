# CR-368: Analytics Timeseries FX Fan-Out Currency Normalization

Date: 2026-05-28

## Scope

Query-service analytics timeseries FX conversion fan-out for portfolio and position analytics
products.

## Finding

`AnalyticsTimeseriesService` still used raw portfolio, reporting, and position currency values when
deciding whether FX maps were needed and when keying position-to-portfolio FX maps. Padded or
lower-case values could:

1. trigger avoidable same-currency FX map requests,
2. request duplicate FX maps for padded aliases such as `EUR` and ` eur `,
3. miss already-loaded canonical FX maps during position conversion,
4. emit non-canonical missing-FX diagnostics.

This mattered because analytics timeseries endpoints fan out FX-map requests across portfolio,
reporting, and position currencies on calculation-facing product paths.

## Change

Reused the shared query-service currency normalizer inside the analytics timeseries service before:

1. portfolio-to-reporting FX map retrieval,
2. position-to-portfolio FX map retrieval,
3. portfolio cashflow conversion checks,
4. portfolio and position timeseries response currency values,
5. missing-FX diagnostics.

Position currency fan-out now deduplicates normalized currency codes and skips normalized
same-currency maps. Position timeseries rows now expose canonical position and cash-flow currency
values.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_analytics_timeseries_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/analytics_timeseries_service.py tests/unit/services/query_service/services/test_analytics_timeseries_service.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a calculation-path
reliability and FX fan-out efficiency hardening slice for analytics input products.
