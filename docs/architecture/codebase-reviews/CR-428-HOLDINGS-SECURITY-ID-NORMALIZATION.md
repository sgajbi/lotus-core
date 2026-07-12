# CR-428: Holdings Security-ID Normalization

Date: 2026-05-28

## Scope

Query-service `HoldingsAsOf:v1` position response assembly and position repository helper
lookups.

## Finding

Holdings assembly still used raw `security_id` values when deduplicating snapshot rows against
history-backed fallback rows, enriching history-backed rows with latest snapshot valuation,
requesting held-since dates, and checking market-price freshness. The related repository helpers
also filtered or grouped by raw persisted security identifiers.

Whitespace drift between daily snapshots, position history, market prices, and request inputs
could therefore double-count one security, miss fallback valuation evidence, miss held-since
lineage, or mark current market-price evidence as stale. That is a calculation-readiness risk for
private banking holdings, downstream performance inputs, and risk explainability.

## Change

Reused the shared query-service security identifier normalizer in holdings service assembly and
position repository helper queries. Holdings responses now emit canonical security identifiers,
deduplicate snapshot/history rows by canonical identifiers, look up fallback valuation and
held-since lineage by canonical identifiers, and request market-price freshness checks with
deduplicated canonical identifiers.

Repository helper SQL now trims persisted security identifiers before filtering, grouping, and
returning keys for held-since date lookup, latest snapshot valuation maps, and latest market-price
date lookup.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_position_service.py tests/unit/services/query_service/repositories/test_unit_query_position_repo.py -q`
2. `python -m ruff check src/services/query_service/app/services/position_service.py src/services/query_service/app/repositories/position_repository.py tests/unit/services/query_service/services/test_position_service.py tests/unit/services/query_service/repositories/test_unit_query_position_repo.py`
3. `python -m pytest tests/unit/services/query_service/services -q`
4. `python -m pytest tests/unit/services/query_service/repositories -q`
5. `git diff --check`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is a holdings
calculation-readiness slice that prevents harmless source identifier padding from changing
position counts, valuation enrichment, lineage dates, or freshness classification.
