# CR-1669: Stale Trust Projection Precedence

## Finding

Reconciliation run aggregation did not rank `STALE`, so stale-only evidence became `UNKNOWN`.
Finding summaries could also overwrite a stale run with `BREAK_OPEN`. Reference coverage reported
stale data quality while projecting freshness as `PARTIAL`, and the same stale-to-partial pattern
was repeated across adjacent market/reference response assemblers.

## Resolution

`portfolio_common.reconciliation_quality` now owns normalized mixed-state aggregation with
fail-closed precedence:
`BLOCKED > STALE > UNKNOWN > UNRECONCILED > BREAK_OPEN > PARTIAL > COMPLETE`. Query Control Plane
reduces run and finding states through that policy. Holdings reconciliation delegates to it while
retaining its empty-scope `UNRECONCILED` contract.

`portfolio_common.market_reference_quality` now owns product-level quality and freshness
projection. Source series, benchmark definitions, compositions and catalogs, index catalogs,
benchmark market windows, and coverage reports preserve blocked, stale, and unknown source quality.
Stale coverage emits `freshness_status=STALE` and `STALE_EVIDENCE`; absent evidence retains the
existing `EMPTY` and `UNAVAILABLE` contract.

## Compatibility

Response schemas, accepted request shapes, persistence, migrations, Kafka contracts, and runtime
topology are unchanged. Response values intentionally change where stale or unknown evidence was
previously collapsed into `PARTIAL` or `UNKNOWN`. Structural completeness remains independently
reported.

OpenAPI schema, domain-product declarations, supported-feature status, and database indexes require
no change because field shapes, product ownership, and query plans are unchanged. RFC, repository
context, review-ledger, and operator wiki truth change because trust interpretation changed.

## Validation

- shared reconciliation, holdings, operations, coverage, and market/reference policy tests;
- source-series, benchmark definition/composition/catalog, index catalog, and market-window tests;
- repository-native RFC-0083, source-data-product, architecture, documentation, wiki, lint, and type
  gates before merge;
- protected PR validation, exact-main validation, and wiki publication/parity before closure.

Issue: #864.
