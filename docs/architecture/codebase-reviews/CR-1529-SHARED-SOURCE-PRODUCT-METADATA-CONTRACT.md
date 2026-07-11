# CR-1529: Shared Source-Product Metadata Contract

Date: 2026-07-12
Issues: #715
Status: Reconciled candidate; complete QCP image closure remains open

## Objective

Give Query Service and Query Control Plane one package-owned source-data runtime metadata contract
without either deployable importing the other's implementation package.

## Finding

The product catalog was already a legitimate shared capability in `portfolio_common`, but response
metadata models, deterministic content hashing, lineage normalization, freshness classification,
and product identity field helpers lived under Query Service DTOs. QCP analytics, integration, and
Core snapshot contracts therefore depended on a Query Service implementation path for shared
source-product semantics.

## Implementation

- Moved the unchanged metadata contract to
  `portfolio_common.source_data_product_metadata` beside the shared product catalog.
- Redirected all Query Service and QCP production and test imports to the canonical module.
- Moved focused metadata tests to the shared-library test boundary.
- Removed the service-local source module without a compatibility facade.

## Compatibility

No response field, default, validation rule, hash algorithm, freshness rule, route, OpenAPI schema,
database object, or runtime topology changed. This is design and package modularity only.

## Source-Branch Validation

- Shared metadata, source-product guard, and domain-contract cohort: `41 passed`.
- Query Service DTO and source-product cohort: `96 passed`.
- QCP unit and integration suite: `335 passed`.
- Source-data product contract guard: passed.
- Scoped Ruff lint/format and full `make architecture-guard`: passed.

Reconciliation validation passed: `221` shared metadata, product-catalog, QCP, documentation, and
guard cases plus direct source-product, architecture-documentation, and wiki guards.

The analytics router retains one existing implicit-return MyPy finding; it is not caused or hidden
by this move and remains in the active analytics ownership slice.

## Same-Pattern Decision

The scan found one shared implementation and 62 imports, not parallel copies. Centralizing the
contract removes that cross-plane dependency root. Service-owned workflows, repositories, and API
contracts remain outside `portfolio_common`; analytics still needs a separate layered QCP move.

## Documentation Decision

Repository context, mesh-data-product wiki source, and the review ledger now name the canonical
owner. No consumer migration note is required because import ownership changed without changing
the public contract.
