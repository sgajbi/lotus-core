# CR-1546: Application-Port Catalog Guard Paths

Date: 2026-07-12
Status: Fixed locally; merge proof pending

## Objective

Keep the application-port capability catalog executable after quality guards were organized under
`scripts/quality/`.

## Finding

The catalog correctly failed closed when two QCP capability entries referenced five obsolete
`scripts/*.py` paths. The guard implementations exist under `scripts/quality/`, so the complete
architecture gate stopped after its earlier boundary checks passed.

## Fix

Updated the analytics-port and Core-snapshot capability entries to reference the actual governed
guard paths. No capability ownership, port contract, runtime behavior, API, or database schema
changed.

## Validation Evidence

- Application-port catalog guard: passed.
- Complete architecture gate: passed.
- JSON, documentation, and wiki guards: passed.
- Repository-wide Ruff lint and format gates: passed (`1778` files formatted).

## Documentation Decision

The catalog and codebase-review ledger are the durable architecture truth for this correction.
README, wiki, repository context, and platform skills do not change because service ownership and
the guard workflow remain unchanged.
