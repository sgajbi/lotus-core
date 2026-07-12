# CR-432: Reporting Snapshot Security-ID Normalization

Date: 2026-05-28

## Scope

Query-service reporting repository latest snapshot rows used by asset allocation and exposure
reporting.

## Finding

`ReportingRepository.list_latest_snapshot_rows(...)` selected latest position-history rows,
reconciled daily snapshots, joined instrument enrichment, and ordered report rows by raw persisted
`security_id` values. Whitespace drift between position history, position state, daily snapshots,
or instruments could create duplicate reporting candidates, prevent snapshot/history
reconciliation, or miss instrument enrichment before allocation calculations ran.

That is a reporting correctness risk because asset-class, sector, region, currency, and
look-through exposure reporting depend on the correct latest holdings candidate and instrument
metadata.

## Change

Moved security identifier canonicalization into the reporting snapshot query boundary. The latest
history subquery now emits and partitions by trimmed security identifiers; position-state joins,
snapshot reconciliation, instrument enrichment, and report ordering now compare or order by
trimmed security identifiers.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_reporting_repository.py -q`
2. `python -m ruff check src/services/query_service/app/repositories/reporting_repository.py tests/unit/services/query_service/repositories/test_reporting_repository.py`
3. `python -m pytest tests/unit/services/query_service/repositories -q`
4. `git diff --check`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is a reporting
calculation-boundary hardening slice that prevents source identifier padding from changing
allocation candidate selection or enrichment.
