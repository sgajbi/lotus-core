# RFC-073 Slice 0 Lint Baseline

Date: `2026-03-05`

## Purpose
Capture a deterministic repository-wide Ruff baseline before slice-by-slice lint hardening.

## Commands
1. `python -m ruff check src tests scripts --statistics`
2. `python -m ruff check src/services --statistics`
3. `python -m ruff check src/libs --statistics`
4. `python -m ruff check tests --statistics`
5. `python -m ruff check scripts --statistics`

## Repo-Wide Baseline
Total findings: `1404`

Rule distribution:
1. `E501 line-too-long`: `1042`
2. `I001 unsorted-imports`: `230`
3. `F401 unused-import`: `113`
4. `E731 lambda-assignment`: `7`
5. `F841 unused-variable`: `6`
6. `F541 f-string-missing-placeholders`: `3`
7. `E402 module-import-not-at-top-of-file`: `1`
8. `E711 none-comparison`: `1`
9. `F811 redefined-while-unused`: `1`

## Domain Breakdown
1. `tests`: `725`
2. `src/services`: `510`
3. `src/libs`: `145`
4. `scripts`: `24`

## Ownership and Execution Order
1. `tests`:
 - owner: test and domain maintainers
 - reason: largest volume and highest readability impact
2. `src/services`:
 - owner: service maintainers
 - reason: runtime-critical code paths
3. `src/libs`:
 - owner: library maintainers
 - reason: shared foundations used across services
4. `scripts`:
 - owner: platform tooling maintainers
 - reason: low volume and fast closure

## Exit Criteria Check
1. Baseline snapshot captured: `yes`
2. Rule and domain breakdown captured: `yes`
3. Ownership/execution sequence documented: `yes`
