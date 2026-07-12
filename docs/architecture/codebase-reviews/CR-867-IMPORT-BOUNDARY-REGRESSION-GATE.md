# CR-867: Import Boundary Regression Gate

Status: Hardened on 2026-06-02.

## Finding

The `.importlinter` scaffold was report-only and not locally runnable from a clean shell because the
`services` and `portfolio_common` packages were not added to the import path. The initial contracts
also over-reported indirect router-to-repository dependencies and intentionally approved shared
FastAPI bootstrap modules.

## Change

Updated `.importlinter` so it enforces the intended boundaries:

1. query-service routers must not directly import query-service repositories,
2. `portfolio_common` FastAPI dependencies must stay limited to approved HTTP and cross-cutting
   modules.

Added:

1. `scripts/import_boundary_gate.py` as a stable entrypoint that sets the repo source path before
   invoking import-linter,
2. `make quality-import-boundary-gate`,
3. a dedicated `Quality Baseline / Import Boundary Gate` workflow job.

## Boundary Preserved

This change does not alter:

1. service orchestration through repositories,
2. approved shared HTTP/bootstrap helpers,
3. runtime behavior,
4. API contracts,
5. database schema.

## Wiki Decision

No repo-local `wiki/` source update is included. This is CI quality-gate governance recorded in the
repo-local quality reports and architecture review ledger; it does not change operator-facing
runtime behavior.

## Validation

Local validation passed for the slice:

1. `make quality-import-boundary-gate`: 2 contracts kept, 0 broken,
2. `make architecture-guard`,
3. `make quality-ruff-gate`,
4. `make quality-ruff-format-gate`,
5. workflow YAML parsing,
6. `git diff --check`.
