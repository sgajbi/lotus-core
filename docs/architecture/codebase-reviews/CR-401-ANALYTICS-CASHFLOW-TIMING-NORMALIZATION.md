# CR-401: Analytics Cashflow Timing Normalization

Date: 2026-05-28

## Scope

Query-service analytics timeseries cash-flow observation construction.

## Finding

Analytics cash-flow observations lowercased source `timing` values without trimming. Padded source
values such as ` EOD ` could therefore leak ` eod ` into downstream analytics source-data product
responses even though the timing code was semantically valid. That creates avoidable risk for
downstream timing predicates, reconciliation views, and generated evidence consumers.

## Change

Trimmed timing before lowercasing in `_build_cash_flow_observation(...)`. Added direct coverage
proving padded upper-case `EOD` emits canonical `eod` while preserving the existing cash-flow type
and flow-scope classification.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_analytics_timeseries_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/analytics_timeseries_service.py tests/unit/services/query_service/services/test_analytics_timeseries_service.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is a
source-data product contract hygiene and analytics cash-flow reliability slice.
