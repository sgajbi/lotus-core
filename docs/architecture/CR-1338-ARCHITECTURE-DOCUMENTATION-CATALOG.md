# CR-1338 Architecture Documentation Catalog

## Scope

Issue cluster: GitHub issue #620.

## Objective

Make the large `docs/architecture/` set searchable and enforceable without requiring engineers or
agents to scan hundreds of review records before finding current-state implementation guidance.

## Changes

1. Added `docs/architecture/architecture-documentation-catalog.v1.json` with explicit metadata for
   current-state architecture guidance, target-model documents, boundary catalogs, review ledgers,
   and historical context.
2. Added coverage rules for large architecture evidence families such as `CR-*`, ADRs, and
   templates so they are intentionally classified without creating a second unmaintainable ledger.
3. Added `scripts/architecture_documentation_catalog_guard.py` and
   `make architecture-docs-catalog-guard`.
4. Wired the guard into `make architecture-guard` and `quality-wiki-docs-gate`.
5. Added focused guard tests for valid catalogs, uncataloged architecture documents, missing
   metadata, invalid statuses, invalid truth roles, and missing navigation links.
6. Linked the catalog from the architecture index, Architecture wiki page, README command list, and
   repo context.

## Behavior And Compatibility

No route path, request DTO, response DTO, OpenAPI schema, database schema, Kafka contract, metric,
runtime topology, package import path, or public runtime behavior changed.

This is a documentation-governance and operability improvement. It reduces design-time complexity
by making current-state architecture truth discoverable and by preventing new architecture docs from
landing without ownership, freshness, status, and truth-role metadata.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/scripts/test_architecture_documentation_catalog_guard.py -q`
2. `python scripts/architecture_documentation_catalog_guard.py`

## Documentation, Wiki, Context, And Skill Decision

Updated the architecture catalog, architecture index, Architecture wiki source, README, repo
context, and review ledger because documentation navigation truth changed.

Wiki source changed and must be published after merge to `main`.

No platform skill source change is required. The repeatable lesson is enforced through a
repo-native catalog guard instead of relying on prose.

## Remaining Work

GitHub issue #620 is locally fixed pending PR CI/QA, post-merge wiki publication, and issue
closure. Future architecture documents must either add an explicit catalog entry or match an
intentional coverage rule.
