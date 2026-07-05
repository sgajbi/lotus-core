# CR-1346 Current-State Architecture Map

Date: 2026-07-05

## Objective

Locally fix GitHub issue #616 by adding a concise, guarded current-state architecture map for
bounded contexts, deployables, data ownership, event/outbox flows, dependency direction, and
downstream consumers.

## Finding

`lotus-core` already had a strong architecture index, RFC target models, runtime-boundary matrix,
and review ledger. New engineers and agents still had to stitch those sources together before
deciding where code belongs. That made it too easy for future slices to put business logic in
routers, persistence models, middleware, scripts, or downstream adapters.

## Changes

1. Added `docs/architecture/current-state-architecture-map.md` with:
   - bounded-context ownership for portfolio/account, transaction booking, positions, valuation,
     cashflow, cost, source-data products, ingestion/replay, reconciliation,
     operations/supportability, security/audit, and platform runtime support,
   - deployable service ownership and prohibited responsibilities,
   - database ownership,
   - dependency direction,
   - event/outbox flow,
   - downstream consumer relationships,
   - cross-links to RFCs, CR records, API catalog/governance entries, and runbooks.
2. Cataloged the map in `docs/architecture/architecture-documentation-catalog.v1.json`.
3. Extended `scripts/architecture_documentation_catalog_guard.py` so the map must:
   - exist,
   - be explicitly cataloged,
   - contain required ownership and freshness anchors,
   - name every deployable service id and service path from
     `docs/architecture/runtime-boundary-decision-catalog.json`.
4. Added guard tests for map freshness and deployable coverage.
5. Linked the map from the architecture index, README, Architecture wiki, microservice boundary
   matrix, and repository engineering context.

## Compatibility Impact

Documentation and validation only. No route path, request DTO, response DTO, OpenAPI schema,
database schema, Kafka topic, event payload, metric name, runtime topology, Dockerfile, deployment
manifest, package import path, or public behavior changed.

This improves design-time modularity and ownership clarity inside the existing deployable
architecture. It does not approve a new runtime split.

## Validation Evidence

Commands to run before commit:

```powershell
python scripts/architecture_documentation_catalog_guard.py
python -m pytest tests/unit/scripts/test_architecture_documentation_catalog_guard.py -q
python -m ruff check scripts/architecture_documentation_catalog_guard.py tests/unit/scripts/test_architecture_documentation_catalog_guard.py --ignore E501,I001
python -m ruff format --check scripts/architecture_documentation_catalog_guard.py tests/unit/scripts/test_architecture_documentation_catalog_guard.py
make quality-wiki-docs-gate
make docs-evidence-pack
git diff --check
```

## Documentation And Wiki Decision

README, architecture index, Architecture wiki, microservice boundary matrix, and
`REPOSITORY-ENGINEERING-CONTEXT.md` changed because architecture ownership truth changed. Wiki
source changed and must be published after merge.

No platform skill change is required; this issue is handled by a repo-local guarded architecture
map and repo context update.
