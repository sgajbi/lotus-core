# CR-424: Core Snapshot Security-ID Normalization

Date: 2026-05-28

## Scope

Query-service `PortfolioStateSnapshot:v1` baseline, simulation, and instrument enrichment
identifier handling.

## Finding

Core snapshot baseline and simulation logic used raw `security_id` values as dictionary keys for
baseline positions, simulation changes, newly introduced instruments, and instrument enrichment
lookups. Whitespace drift in source rows or simulation changes could create duplicate projected
positions, miss baseline rows, miss instrument enrichment, or send padded identifiers to market
price lookup.

That failure mode can make simulated portfolio quantities, market values, deltas, and enrichment
evidence incorrect even when the authoritative data is present.

## Change

Reused the shared query-service security identifier normalizer in core snapshot assembly. Baseline
position keys and emitted position identities are trimmed, simulation changes are normalized before
missing-instrument detection and quantity application, returned instruments are keyed by normalized
identifier, and instrument enrichment bulk lookup can match padded repository-returned instrument
identifiers to canonical caller identifiers.

Blank simulation-change identifiers now fail closed with an explicit unavailable-section error
instead of creating an ambiguous projected position key.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_core_snapshot_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/core_snapshot_service.py tests/unit/services/query_service/services/test_core_snapshot_service.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is a
calculation-correctness slice that keeps portfolio snapshot and simulation outputs from drifting
because of whitespace in source or simulation security identifiers.
