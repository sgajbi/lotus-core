# CR-1640: Cashflow Runtime Trust And Calculation Lineage

## Objective

Resolve GitHub issue #796 by making `PortfolioCashflowProjection:v1` and
`PortfolioCashMovementSummary:v1` authoritative, tenant-bindable runtime receipts whose source
inputs, versioned calculation, and returned outputs are independently identifiable.

## Finding

Both products returned useful cashflow values but treated successful response construction as
`COMPLETE`. They did not compare output totals/counts to source-query controls, did not distinguish a
valid empty window from unavailable evidence, and omitted deterministic request/snapshot identity
and three-layer calculation lineage. Movement metadata also hard-coded current evidence, while a
projection content hash did not bind tenant scope.

## Change

- Extended existing grouped SQL reads with source-row and source-total windows in the same query.
  Movement controls remain per currency; unlike currencies are never netted.
- Added one narrow Query Service cashflow-window trust policy shared by the two products. A zero-row
  window is `COMPLETE`, `SUPPORTED`, `EMPTY_SOURCE_WINDOW` with no invented timestamp. Count, total,
  or populated-timestamp contradictions are `BLOCKED` and `UNAVAILABLE`.
- Bound optional `X-Tenant-Id`, the exact bounded request, source rows and controls, algorithm id,
  version, 50-digit Decimal precision, and returned values through separate input, calculation, and
  output SHA-256 hashes.
- Published deterministic request, snapshot, content/source-digest, policy, source-reference, and
  correlation metadata. Correlation remains operational and is excluded from financial hashes.
- Updated existing OpenAPI DTOs, methodology pages, RFC-0083 catalog, repository context, source
  product declarations, methodology index, and repo-local wiki source rather than creating a
  parallel documentation framework.

## Compatibility And Ownership

The change is additive at the HTTP boundary. Existing cashflow amounts, grouping, signs, date
selection, projected-mode behavior, and route paths remain unchanged. No migration, event, Kafka,
cashflow-generation, accounting, liquidity, performance, advice, treasury, tax, or OMS contract
changed. Cashflow product calculations and the narrow trust policy remain in Query Service;
framework-independent calculation hashing stays in `portfolio_common`.

## Validation

- Full Query Service unit suite: `621 passed`.
- Isolated PostgreSQL proof: exact latest-epoch series row-count/total and movement row-count/
  per-currency controls each passed against the real grouped window queries.
- Full MyPy: no issues across `237` source files.
- Full Ruff lint and format gates: `2,054` files clean.
- Architecture, domain, application, port, adapter, source-product, OpenAPI, vocabulary, route
  catalog, documentation catalog, supported-features, wiki, and front-door guards passed.
- Signed implementation commits: `3edef1518`, `4de482919`, `d6baba05d`, `4f31ebac8`, and
  `5fde725c1`; PostgreSQL and degraded-contract proof: `a9bffb05c`, `5f737aec9`.

No migration, event, Kafka, ingestion, persistence schema, or generated cashflow truth changed.
PR CI, exact-main validation, wiki publication, and downstream Idea consumption remain post-local
closure gates.
