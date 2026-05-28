# CR-434: Instrument Security-ID Normalization

Date: 2026-05-28

## Scope

Query-service instrument service and repository lookup boundaries.

## Finding

Instrument lookup filtered `instruments.security_id` with raw equality or `IN` predicates, and
the instrument service passed request identifiers through as supplied. Padded identifiers could
miss instrument enrichment for simulations, snapshots, reporting, and lookup APIs. Padded stored
identifiers could also leak into response DTOs.

That is a calculation and metadata quality risk because instrument enrichment supplies asset
class, product type, sector, country of risk, rating, liquidity tier, and currency context used by
private banking analytics.

## Change

Reused the shared query-service security identifier normalizer across the instrument service and
repository. Bulk instrument lookup now deduplicates and trims requested identifiers, skips blank
identifiers, and filters against `trim(instruments.security_id)`. Paginated lookup/count filters
now use canonical request identifiers and trimmed SQL comparisons. The service emits canonical
`security_id` values in `InstrumentRecord` responses.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_instrument_repository.py tests/unit/services/query_service/services/test_instrument_service.py -q`
2. `python -m ruff check src/services/query_service/app/repositories/instrument_repository.py src/services/query_service/app/services/instrument_service.py tests/unit/services/query_service/repositories/test_instrument_repository.py tests/unit/services/query_service/services/test_instrument_service.py`
3. `python -m pytest tests/unit/services/query_service/repositories -q`
4. `python -m pytest tests/unit/services/query_service/services -q`
5. `git diff --check`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is an
enrichment-boundary hardening slice that protects calculations and product views from missing or
non-canonical instrument metadata due to identifier padding.
