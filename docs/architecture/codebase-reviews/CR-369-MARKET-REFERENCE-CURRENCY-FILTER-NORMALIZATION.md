# CR-369: Market Reference Currency Filter Normalization

Date: 2026-05-28

## Scope

Query-service market/reference repository filters used by benchmark, index, and risk-free source
data products.

## Finding

`ReferenceDataRepository` still normalized selected market-reference currency filters with raw
`.upper()` calls. Padded lower-case request values such as ` usd ` could compile SQL predicates
against ` USD ` instead of canonical `USD`, causing benchmark definitions, index definitions, or
risk-free series lookups to miss bank-owned reference rows.

This mattered because these reference products support analytics and downstream calculation
consumers that need deterministic benchmark, index, and risk-free inputs.

## Change

Reused the shared query-service currency normalizer before building SQL predicates for:

1. benchmark definition currency filters,
2. index definition currency filters,
3. risk-free series currency filters.

The predicates remain index-friendly constant comparisons against canonical currency codes and do
not add column-side functions.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_reference_data_repository.py -q`
2. `python -m pytest tests/unit/services/query_service/repositories -q`
3. `python -m ruff check src/services/query_service/app/repositories/reference_data_repository.py tests/unit/services/query_service/repositories/test_reference_data_repository.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a repository-boundary
reliability hardening slice for market/reference data lookup correctness.
