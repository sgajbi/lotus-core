# CR-376: Analytics Cash-Book Position Normalization

Date: 2026-05-28

## Scope

Query-service analytics timeseries cash-book classification used by beginning-market-value
continuity for position-derived portfolio observations.

## Finding

`AnalyticsTimeseriesService._is_cash_book_position` case-normalized asset-class and security-id
values without trimming source whitespace. Padded lower-case values such as ` cash ` could prevent
cash-book rows from using the cash-settlement beginning-market-value rule, causing internal cash
book settlement days to use a non-cash continuity path.

This mattered because beginning-market-value continuity feeds portfolio and position performance
time-series observations.

## Change

Trimmed asset-class and security-id control codes before cash-book classification. Added a focused
regression test proving padded `cash` asset-class values select the cash-book settlement branch and
produce the expected beginning-market-value result.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_analytics_timeseries_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/analytics_timeseries_service.py tests/unit/services/query_service/services/test_analytics_timeseries_service.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a calculation-path
reliability hardening slice for existing analytics source-data products.
