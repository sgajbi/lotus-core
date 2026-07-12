# CR-866: Ruff Format Regression Gate

Status: Hardened on 2026-06-02.

## Finding

After CR-865, repository-wide Ruff format was clean, but the quality-baseline workflow still
enforced only Ruff lint. The repo also did not expose a dedicated full-repository Ruff format make
target for local parity.

## Change

Added:

1. `make quality-ruff-format-gate`,
2. a dedicated `Quality Baseline / Ruff Format Gate` workflow job that runs
   `python -m ruff format --check .`.

The remaining baseline tools stay report-only until their baselines are truthful and stable enough
for regression enforcement.

## Boundary Preserved

This change does not alter:

1. runtime behavior,
2. API contracts,
3. database schema,
4. existing Ruff lint gate behavior,
5. report-only posture for the remaining quality tools.

## Wiki Decision

No repo-local `wiki/` source update is included. This is CI quality-gate governance recorded in the
repo-local quality reports and architecture review ledger; it does not change operator-facing
runtime behavior.

## Validation

Local validation passed for the slice:

1. `make quality-ruff-format-gate`,
2. `make quality-ruff-gate`,
3. workflow YAML parsing,
4. quality workflow grep for the Ruff format job,
5. `git diff --check`.
