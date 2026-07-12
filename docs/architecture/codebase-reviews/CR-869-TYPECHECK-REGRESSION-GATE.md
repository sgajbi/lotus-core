# CR-869: Typecheck Regression Gate

Status: Hardened on 2026-06-02.

## Finding

The configured mypy scope was clean but not enforced in the quality-baseline workflow. `mypy.ini`
also carried a stale `[mypy-tests.*]` section even though the configured `files` scope does not
include tests, causing successful typecheck output to include unused-config noise.

Security is not ready for enforcement yet. Local Bandit measurement currently reports 17 findings:
5 low, 11 medium, and 1 high.

## Change

Added a dedicated `Quality Baseline / Typecheck Gate` workflow job that runs:

1. `python -m mypy --config-file mypy.ini`.

Also:

1. removed the stale unused mypy test section,
2. retained a report-only typecheck baseline step in the report-only job for artifact continuity,
3. recorded the current Bandit baseline in the quality evidence.

## Boundary Preserved

This change does not alter:

1. runtime behavior,
2. API contracts,
3. database schema,
4. current configured mypy source scope,
5. report-only security posture.

## Wiki Decision

No repo-local `wiki/` source update is included. This is CI quality-gate governance recorded in the
repo-local quality reports and architecture review ledger; it does not change operator-facing
runtime behavior.

## Validation

Local validation passed for the slice:

1. `make typecheck`,
2. `make quality-ruff-gate`,
3. `make quality-ruff-format-gate`,
4. `make quality-import-boundary-gate`,
5. `make openapi-gate`,
6. `make api-vocabulary-gate`,
7. Bandit baseline measurement,
8. workflow YAML parsing,
9. `git diff --check`.
