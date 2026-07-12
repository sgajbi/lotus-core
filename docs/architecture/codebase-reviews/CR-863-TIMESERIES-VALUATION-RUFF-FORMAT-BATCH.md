# CR-863: Timeseries Valuation Ruff Format Batch

Status: Hardened on 2026-06-02.

## Finding

After CR-862, Ruff lint was clean and enforced, but full `ruff format --check .` still reported 52
files requiring formatting. The next bounded subset covered timeseries generator and
valuation-orchestrator runtime files plus closest focused tests.

## Change

Ran Ruff formatting against selected files under:

1. `src/services/timeseries_generator_service/`,
2. `src/services/valuation_orchestrator_service/`,
3. focused valuation and timeseries tests.

The repository-wide format baseline is down from 52 files to 40 files requiring formatting.

## Boundary Preserved

This change does not alter:

1. timeseries consumer behavior,
2. valuation scheduler behavior,
3. valuation repository behavior,
4. API contracts,
5. database schema,
6. migration graph shape.

## Wiki Decision

No repo-local `wiki/` source update is included. This is mechanical formatting of runtime service
files and focused tests with no operator-facing behavior change.

## Validation

Local validation passed for the slice:

1. scoped `python -m ruff format --check <batch>`,
2. `make quality-ruff-gate`,
3. `python -m ruff format --check .` baseline measurement,
4. `python -m py_compile <batch>`,
5. focused valuation/timeseries tests and collection checks,
6. `git diff --check`.
