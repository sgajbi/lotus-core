# CR-437: Look-Through Component Security-ID Normalization

Date: 2026-05-28

## Scope

Query-service reporting repository look-through component resolution used by asset-allocation
reporting.

## Finding

`ReportingRepository.list_instrument_lookthrough_components(...)` normalized requested parent
security identifiers, but component identifiers were still selected, ordered, and joined to
instrument metadata using raw persisted values. Whitespace drift on component identifiers could
miss instrument enrichment for look-through exposures or emit padded component identifiers into
allocation calculations.

That is an exposure and allocation correctness risk because source-owned look-through rows are used
to decompose fund holdings before region, asset-class, and other allocation views are calculated.

## Change

Reused the shared query-service security identifier normalizer on the component side of
look-through resolution. The repository now trims component identifiers in select/order clauses,
joins instrument metadata through trimmed instrument/component identifiers, excludes blank
component identifiers, and returns canonical parent and component security identifiers.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_reporting_repository.py -q`
2. `python -m ruff check src/services/query_service/app/repositories/reporting_repository.py tests/unit/services/query_service/repositories/test_reporting_repository.py`
3. `python -m pytest tests/unit/services/query_service/repositories -q`
4. `python -m pytest tests/unit/services/query_service/services -q`
5. `git diff --check`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is a reporting
allocation hardening slice that prevents source identifier padding from breaking look-through
component enrichment and exposure decomposition.
