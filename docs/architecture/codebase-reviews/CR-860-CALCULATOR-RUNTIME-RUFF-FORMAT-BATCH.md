# CR-860: Calculator Runtime Ruff Format Batch

Status: Hardened on 2026-06-02.

## Finding

After CR-859, Ruff lint was clean and enforced, but full `ruff format --check .` still reported 110
files requiring formatting. The next bounded subset covered calculator, valuation, reconciliation,
and persistence runtime files plus the closest focused tests.

## Change

Ran Ruff formatting against selected files under:

1. `src/services/calculators/`,
2. `src/services/financial_reconciliation_service/`,
3. `src/services/persistence_service/`,
4. focused calculator, reconciliation, and persistence tests.

The repository-wide format baseline is down from 110 files to 90 files requiring formatting.

## Boundary Preserved

This change does not alter:

1. calculator consumer behavior,
2. valuation repository behavior,
3. financial reconciliation DTO shape,
4. persistence consumer behavior,
5. API contracts,
6. database schema or migration graph shape.

## Wiki Decision

No repo-local `wiki/` source update is included. This is mechanical formatting of runtime service
files and focused tests with no operator-facing behavior change.

## Validation

Local validation passed for the slice:

1. scoped `python -m ruff format --check <batch>`,
2. `make quality-ruff-gate`,
3. `python -m ruff format --check .` baseline measurement,
4. `python -m py_compile <batch>`,
5. focused runtime tests and collection checks,
6. `git diff --check`.
