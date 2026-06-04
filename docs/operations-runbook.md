# lotus-core Operations Runbook

## Purpose

This runbook summarizes operator-facing posture for `lotus-core` quality, readiness, and validation.
Detailed product and scenario-specific runbooks remain under `docs/operations/`.

## Initial Quality Baseline Commands

```powershell
python -m ruff check . --statistics
python -m pytest --collect-only -q
python -m radon cc src -s -a
python -m radon mi src -s
python scripts\migration_contract_check.py --mode alembic-sql
```

## CI Posture

1. Existing feature and PR gates remain authoritative for merge readiness.
2. `Quality Baseline Report` is report-only and should not block PRs yet.
3. The baseline should ratchet from report-only to regression-only once collection and tool
   availability are stable.

## Escalation

Treat new collection failures, new architecture-boundary violations, new security findings, and new
OpenAPI regressions as release risks even while legacy baseline debt is being ratcheted down.
