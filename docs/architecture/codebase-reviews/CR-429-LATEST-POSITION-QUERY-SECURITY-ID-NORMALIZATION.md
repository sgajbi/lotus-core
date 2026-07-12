# CR-429: Latest Position Query Security-ID Normalization

Date: 2026-05-28

## Scope

Query-service latest holdings repository queries for daily snapshot and position-history backed
positions.

## Finding

After CR-428, holdings assembly normalized identifiers after repository results were returned, but
the repository queries that decide which snapshot or history row is latest still partitioned and
joined on raw persisted `security_id` values. Padded and unpadded rows for the same bank security
could therefore survive as separate latest candidates, fail to reconcile against current
position-history quantity, or miss instrument and position-state enrichment before service-level
deduplication had a chance to repair the response.

That is a correctness and lineage risk for private banking holdings because the wrong candidate
row can change quantity, valuation freshness, reprocessing status, and downstream analytics input
selection.

## Change

Moved security identifier canonicalization into the latest-position query boundary. The daily
snapshot latest-row queries now partition by trimmed snapshot security identifier, join to the
latest current position-history subquery by trimmed identifier, and join instruments and
position-state rows by trimmed identifiers. The position-history fallback queries and the shared
latest-current history subquery now partition and join by trimmed history/state identifiers.

The specific returned ORM rows are unchanged; service-level DTO assembly continues to emit
canonical identifiers from CR-428.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_unit_query_position_repo.py -q`
2. `python -m ruff check src/services/query_service/app/repositories/position_repository.py tests/unit/services/query_service/repositories/test_unit_query_position_repo.py`
3. `python -m pytest tests/unit/services/query_service/repositories -q`
4. `git diff --check`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is a repository
query-boundary hardening slice that prevents identifier padding from changing latest-position
candidate selection or enrichment joins.
