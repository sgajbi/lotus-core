# CR-378: Portfolio Summary Valuation Status Normalization

Date: 2026-05-28

## Scope

Query-service `PortfolioSummary` valuation coverage counts.

## Finding

`ReportingService.get_portfolio_summary` uppercased snapshot `valuation_status` values without
trimming source whitespace. Padded lower-case values such as ` unvalued ` could be counted as valued
positions, overstating valuation coverage and understating unvalued positions in portfolio summary
metadata.

This mattered because portfolio summary metadata is used as an operational quality signal for
private banking reporting and downstream advisory/performance workflows.

## Change

Added a small reporting-service control-code normalizer and reused it for `UNVALUED` status
classification. Updated the portfolio summary test fixture to prove padded lower-case valuation
status values still produce the correct valued and unvalued counts.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_reporting_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/reporting_service.py tests/unit/services/query_service/services/test_reporting_service.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a source-data
quality metadata reliability hardening slice for the existing portfolio summary product.
