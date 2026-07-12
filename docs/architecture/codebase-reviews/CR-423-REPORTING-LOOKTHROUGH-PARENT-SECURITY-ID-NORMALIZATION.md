# CR-423: Reporting Look-Through Parent Security-ID Normalization

Date: 2026-05-28

## Scope

Query-service reporting allocation look-through resolution and reporting repository component
lookup.

## Finding

Asset-allocation look-through resolution passed raw holding `security_id` values into the
instrument look-through repository and grouped returned components by raw `parent_security_id`.
Whitespace drift in a fund or structured-product parent identifier could prevent a complete
component decomposition from being applied, leaving the allocation at direct-holding level and
misstating asset-class, region, sector, and currency exposure.

The repository predicate also used a raw `parent_security_id IN (...)` comparison, so request-side
padding could miss otherwise valid component rows.

## Change

Introduced a shared query-service security identifier normalizer and reused it in cash-balance and
reporting paths. Reporting allocation now trims parent holding identifiers before repository
lookup, trims returned component parent identifiers before grouping, and checks decomposition
support against normalized parent identifiers.

The reporting repository now trims `instrument_lookthrough_components.parent_security_id` in the
lookup predicate and selected parent key so persisted whitespace drift does not block source-owned
look-through decomposition.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_reporting_service.py tests/unit/services/query_service/repositories/test_reporting_repository.py tests/unit/services/query_service/services/test_cash_balance_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m pytest tests/unit/services/query_service/repositories -q`
4. `python -m ruff check src/services/query_service/app/repositories/identifier_normalization.py src/services/query_service/app/services/cash_balance_service.py src/services/query_service/app/services/reporting_service.py src/services/query_service/app/repositories/reporting_repository.py tests/unit/services/query_service/services/test_cash_balance_service.py tests/unit/services/query_service/services/test_reporting_service.py tests/unit/services/query_service/repositories/test_reporting_repository.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is a reporting
calculation correctness slice that keeps allocation look-through decomposition from silently
falling back to direct holdings because of whitespace drift in parent security identifiers.
