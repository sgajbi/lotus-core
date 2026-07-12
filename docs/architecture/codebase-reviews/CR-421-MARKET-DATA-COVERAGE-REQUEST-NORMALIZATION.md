# CR-421: Market Data Coverage Request Normalization

Date: 2026-05-28

## Scope

Query-service `MarketDataCoverageWindow:v1` service-boundary request normalization.

## Finding

`get_market_data_coverage(...)` passed raw requested instrument identifiers into latest-market-price
lookup and used the same raw values for coverage joins. A padded instrument identifier could miss an
available price observation and incorrectly mark DPM market-data supportability incomplete.

The same service returned `valuation_currency` exactly as supplied. A lowercase currency such as
`sgd` could leak into source-data product metadata even though Lotus currency identity is expected
to use canonical ISO uppercase form.

## Change

Trimmed requested instrument identifiers at the service boundary before repository lookup, coverage
join, returned coverage records, and supportability missing/stale lists. Normalized optional
valuation currency with the existing query-service currency-code normalizer before returning the
source-data product response.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_integration_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/integration_service.py tests/unit/services/query_service/services/test_integration_service.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is a
service-boundary correctness slice that keeps DPM market-data readiness from falsely missing prices
because of caller whitespace and keeps currency metadata canonical.
