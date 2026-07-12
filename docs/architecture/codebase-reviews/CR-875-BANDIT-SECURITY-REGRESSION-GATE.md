# CR-875: Bandit Security Regression Gate

Status: Hardened on 2026-06-02.

## Finding

After CR-874, `python -m bandit -r src -c pyproject.toml` reported zero findings. The clean
security baseline was still only measured locally and in the report-only quality job, so future
Python security regressions could remain non-blocking in the quality-baseline workflow.

## Change

Added:

1. `make quality-bandit-gate`,
2. a dedicated `Quality Baseline / Bandit Security Gate` workflow job that installs Bandit and
   runs `python -m bandit -r src -c pyproject.toml`.

The report-only workflow still keeps broader security and dependency-audit visibility, including
`pip-audit`.

## Boundary Preserved

This change does not alter:

1. runtime behavior,
2. API contracts,
3. database schema,
4. existing report-only dependency-audit posture,
5. existing enforced Ruff, import-boundary, API-governance, and typecheck jobs.

## Wiki Decision

No repo-local `wiki/` source update is included. This is CI quality-gate governance recorded in the
repo-local quality reports and architecture review ledger; it does not change operator-facing
runtime behavior.

## Validation

Local validation passed for the slice:

1. `make quality-bandit-gate`,
2. `make quality-ruff-gate`,
3. `make quality-ruff-format-gate`,
4. `make typecheck`,
5. workflow YAML parsing,
6. quality workflow grep for the Bandit security gate,
7. `git diff --check`.
