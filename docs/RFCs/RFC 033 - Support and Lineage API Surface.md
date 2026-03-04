# RFC 033 - Support and Lineage API Surface

- Date: 2026-02-23
- Services Affected: `query-service`
- Status: Implemented (Phase 1)

## Summary

This RFC standardizes support and lineage observability via API endpoints so operations do not require direct database access for routine diagnostics.

## Implemented Endpoints

1. `GET /support/portfolios/{portfolio_id}/overview`
2. `GET /lineage/portfolios/{portfolio_id}/securities/{security_id}`

## Response Scope

1. Reprocessing state (`epoch`, `watermark`, status)
2. Queue pressure indicators (valuation/aggregation pending counts)
3. Latest data availability markers (transactions, snapshots, valuation jobs)

## OpenAPI Quality

1. Added explicit descriptions and examples on all new attributes.
2. Added explicit endpoint summaries and descriptions.

## Phase 2

1. Add correlation-driven event trace APIs (`correlation_id` lineage across outbox and consumers).
2. Add support APIs for dead-letter state and replay history.
3. Add role-based access policy for support endpoints once AuthN/AuthZ RFC is implemented.
