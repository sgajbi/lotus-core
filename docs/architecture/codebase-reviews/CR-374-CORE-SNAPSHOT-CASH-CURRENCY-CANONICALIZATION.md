# CR-374: Core Snapshot Cash and Currency Canonicalization

Date: 2026-05-28

## Scope

Query-service `PortfolioStateSnapshot` valuation context metadata, baseline cash filtering, and
projected-position cash filtering.

## Finding

`CoreSnapshotService` normalized currencies for FX lookup internals, but still resolved valuation
context metadata from raw portfolio or request values. Its cash inclusion checks also uppercased
asset-class values without trimming source whitespace. Padded lower-case values such as ` cash `
could:

1. bypass `include_cash_positions=false` in baseline position assembly,
2. remain in projected-position outputs when cash rows should be excluded,
3. distort portfolio totals and position weights by including cash exposure unexpectedly,
4. echo non-canonical portfolio or reporting currency metadata even when FX calls used canonical
   currency pairs.

This mattered because core snapshot output is a governed source-data product consumed by
downstream performance, advisory, and reporting calculations.

## Change

Added a small core-snapshot control-code normalizer and shared cash asset-class predicate for
baseline and projected position filtering. Canonicalized portfolio and reporting currencies before
FX resolution, simulation projection, and valuation context response construction.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_core_snapshot_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/core_snapshot_service.py tests/unit/services/query_service/services/test_core_snapshot_service.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a calculation-path
and metadata reliability hardening slice for the existing core snapshot source-data product.
