# CR-570: Supported Features Wiki Current State

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

The repo wiki had useful operator and subsystem pages, but it did not have a dedicated
implementation-backed current-state feature page for business users, operations, sales, client-demo
preparation, and engineering. That made feature claims harder to reuse safely outside deep RFCs,
mesh-product docs, or code review ledger entries.

## Change

Added `wiki/Supported-Features.md` and linked it from `wiki/Home.md` and `wiki/_Sidebar.md`.

The page provides:

1. current implementation-backed capability map,
2. functional and integration Mermaid diagrams,
3. functional capability detail,
4. non-functional capability matrix,
5. demo and pitch guidance with safe claims and owner boundaries,
6. current limitations,
7. evidence links into route, data-product, architecture, operations, and migration sources.

## Impact

The repo-local wiki source is more useful for business, operations, sales, client-demo, and
engineering audiences without overclaiming target-state behavior. It keeps Core capability claims
anchored to implementation evidence and separates Core source truth from downstream performance,
risk, advisory, reporting, management, gateway, and Workbench ownership.

Wiki publication must wait until after this branch is merged to `main`.

## Validation

Local validation passed:

1. linked-path check for the new wiki page and referenced repo artifacts - passed
2. `rg "Supported Features|```mermaid|Current Capability Map|Non-Functional Capability Matrix|Demo And Pitch Guidance" wiki/Supported-Features.md wiki/Home.md wiki/_Sidebar.md` - passed
3. `git diff --check` - passed
4. `../lotus-platform/automation/Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core` - expected unmerged-branch published wiki drift for `_Sidebar.md`, `Database-Migrations.md`, `Home.md`, and `Supported-Features.md`
