# CR-871: Production Assert Guard Hardening

Status: Hardened on 2026-06-02.

## Finding

After CR-870, Bandit still reported four low-severity `B101` findings in production source.
Those findings were runtime guards implemented with `assert` in:

1. operations route required-date parsing,
2. analytics export request narrowing,
3. core snapshot simulation-option narrowing.

Assertions can be disabled under optimized Python, so these guards should be explicit runtime
checks even when upstream DTO/FastAPI validation normally prevents the malformed states.

## Change

Replaced production asserts with explicit guards:

1. `parse_required_iso_date(...)` for required operations route dates,
2. `AnalyticsInputError` guards for malformed analytics export request shapes,
3. `CoreSnapshotBadRequestError` guard for simulation mode without simulation options.

Added focused tests for the malformed runtime states.

The Bandit baseline is reduced from 16 findings to 12 findings, with zero high-severity findings
remaining.

## Boundary Preserved

This change preserves:

1. existing request validation semantics,
2. existing service error taxonomy,
3. API contracts,
4. database schema,
5. report-only security posture until the remaining findings are fixed or explicitly governed.

## Wiki Decision

No repo-local `wiki/` source update is included. This is a security hardening and quality-baseline
ratchet recorded in the repo-local quality reports and architecture review ledger; it does not
change operator-facing runtime behavior.

## Validation

Local validation passed for the slice:

1. focused analytics-timeseries, core-snapshot, and operations-router tests: 159 passed,
2. `python -m bandit -r src -c pyproject.toml` baseline measurement: 12 findings, 0 high,
3. source assert search over touched production files: no matches,
4. `make quality-ruff-gate`,
5. `make quality-ruff-format-gate`,
6. `make typecheck`,
7. `git diff --check`.
