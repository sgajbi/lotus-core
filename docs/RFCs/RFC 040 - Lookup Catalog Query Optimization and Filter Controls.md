# RFC 040 - Lookup Catalog Query Optimization and Filter Controls

- Status: IMPLEMENTED
- Date: 2026-02-23
- Owners: lotus-core Query Service

## Context

lotus-core lookup APIs were introduced as canonical selector contracts. To support enterprise-scale UI selectors and reduce payload size, lookup catalogs require server-side filtering and deterministic ordering.

## Decision

Enhance lotus-core lookup APIs with query controls and deterministic output behavior:

- `GET /lookups/portfolios`
  - Added: `cif_id`, `booking_center`, `q`, `limit`
- `GET /lookups/instruments`
  - Added: `product_type`, `q`
- `GET /lookups/currencies`
  - Added: `source` (`ALL|PORTFOLIOS|INSTRUMENTS`), `q`, `limit`

Behavior changes:
- Lookup items are sorted deterministically by `id`.
- `q` performs case-insensitive matching on `id`/`label`.
- `limit` is enforced server-side to protect UI and lotus-gateway from oversized catalogs.

## Rationale

- Improves selector responsiveness and API efficiency.
- Moves filtering concerns to lotus-core where catalog ownership resides.
- Establishes stable, deterministic lookup payloads for repeatable UI behavior.

## Consequences

Positive:
- Smaller payloads and faster client-side rendering.
- Better tenancy/business-unit scoping for portfolio selectors.
- Cleaner integration path for lotus-gateway and UI.

Trade-offs:
- Slightly expanded API surface and parameter validation matrix.

## Follow-ups

- Introduce pagination token patterns for very large catalogs if needed.
- Add tenant/entitlement-aware lookup filtering once access-control model is finalized.
