# CR-865: E2E Advisory Ruff Format Completion

Status: Hardened on 2026-06-02.

## Finding

After CR-864, Ruff lint was clean and enforced, but full `ruff format --check .` still reported 21
files requiring formatting. The remaining debt was isolated to E2E workflow tests and
query-service advisory-simulation unit tests.

## Change

Ran Ruff formatting against the remaining files under:

1. `tests/e2e/`,
2. `tests/unit/services/query_service/advisory_simulation/`.

The repository-wide format baseline is now clean: `python -m ruff format --check .` reports 1,070
files already formatted.

## Boundary Preserved

This change does not alter:

1. E2E workflow assertions,
2. advisory-simulation assertions,
3. API contracts,
4. database schema,
5. live-stack execution posture.

## Wiki Decision

No repo-local `wiki/` source update is included. This is mechanical formatting of E2E and unit test
files with no operator-facing behavior change.

## Validation

Local validation passed for the slice:

1. repository-wide `python -m ruff format --check .`,
2. `make quality-ruff-gate`,
3. `python -m py_compile <batch>`,
4. focused advisory-simulation unit tests: 41 passed,
5. E2E collection: 38 tests collected,
6. `git diff --check`.
