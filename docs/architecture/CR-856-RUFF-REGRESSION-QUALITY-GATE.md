# CR-856: Ruff Regression Quality Gate

Status: Hardened on 2026-06-02.

## Finding

CR-855 made repository-wide Ruff clean, but the quality-baseline workflow still ran Ruff as a
report-only step. That meant a pull request could reintroduce Ruff findings without failing the
dedicated progressive quality workflow.

## Change

Added a repo-native `make quality-ruff-gate` target and a dedicated
`Quality Baseline / Ruff Regression Gate` job in `.github/workflows/quality-baseline.yml`.

The existing report-only job remains in place for tools whose baselines are not yet clean, including
test collection, complexity, maintainability, dead code, dependency usage, security, import
boundaries, and docstrings.

## Boundary Preserved

This change does not alter:

1. runtime service behavior,
2. API contracts,
3. database schema,
4. migration graph shape,
5. existing feature-lane targets,
6. report-only baseline visibility for not-yet-clean tools.

## Explicit Non-Goal

Full `ruff format --check .` is not enforced in this slice. Local evidence shows the repository
still has a separate format baseline, so format enforcement needs its own cleanup and validation
slice.

## Wiki Decision

No repo-local `wiki/` source update is included. This is CI quality-gate governance recorded in the
repository quality docs and architecture review ledger.

## Validation

Local validation passed for the slice:

1. `make quality-ruff-gate`,
2. workflow YAML parse check,
3. quality workflow content check,
4. `python -m ruff check . --statistics`,
5. `git diff --check`.
