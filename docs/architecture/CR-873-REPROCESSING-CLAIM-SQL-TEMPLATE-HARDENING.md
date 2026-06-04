# CR-873: Reprocessing Claim SQL Template Hardening

Status: Hardened on 2026-06-02.

## Finding

After CR-872, Bandit still reported one low-confidence medium `B608` finding in the shared
reprocessing job repository. The flagged path built the worker claim SQL with an interpolated
`ORDER BY` clause.

The interpolation was internally selected from fixed values, not request-controlled input, but the
pattern still created avoidable scanner noise in a shared operational reliability path.

## Change

Replaced the interpolated claim SQL with explicit static query templates selected by job type:

1. reset-watermarks claims order by earliest impacted date, then creation time, then id,
2. generic claims order by creation time, then id.

Both templates retain the atomic `UPDATE ... WHERE id IN (...) RETURNING *` claim shape with
`FOR UPDATE SKIP LOCKED`.

The Bandit baseline is reduced from 11 findings to 10 findings, with zero low-severity and
zero high-severity findings remaining.

## Boundary Preserved

This change preserves:

1. reset-watermarks duplicate normalization before claim,
2. reset-watermarks priority ordering,
3. generic job creation-order claiming,
4. worker concurrency behavior,
5. API contracts,
6. database schema,
7. report-only security posture until the remaining medium findings are fixed or explicitly
   governed.

## Remaining Security Baseline

Bandit now reports 10 medium `B104` findings for health-probe Uvicorn bind-all host literals in
consumer managers. These are the remaining security-hardening targets before the Bandit gate can be
enforced.

## Wiki Decision

No repo-local `wiki/` source update is included. This is a security baseline cleanup recorded in
the repo-local quality reports and architecture review ledger; it does not change operator-facing
runtime behavior.

## Validation

Local validation passed for the slice:

1. `python -m pytest tests\unit\libs\portfolio-common\test_reprocessing_job_repository.py -q`:
   18 passed,
2. `python -m bandit -r src -c pyproject.toml` baseline measurement: 10 findings, 0 low, 0 high,
3. `make quality-ruff-gate`,
4. `make quality-ruff-format-gate`,
5. `make typecheck`,
6. `git diff --check`.
