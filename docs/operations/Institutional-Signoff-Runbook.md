# Institutional Sign-Off Runbook

## Purpose
Provide a deterministic, auditable sign-off flow for institutional readiness before go-live.

## Required Evidence Inputs
Evidence must come from the latest generated artifacts in `output/task-runs`:
1. `*-docker-endpoint-smoke.json`
2. `*-latency-profile.json`
3. `*-performance-load-gate.json` (full tier)
4. `*-failure-recovery-gate.json`

## Generate Sign-Off Pack
Run:

```powershell
make test-institutional-signoff-pack
```

This command writes:
1. `output/task-runs/*-institutional-signoff-pack.json`
2. `output/task-runs/*-institutional-signoff-pack.md`

## Go-Live Checklist
All items must be `yes`:
1. Docker endpoint smoke passed.
2. Latency profile has zero endpoint violations (`p95 <= budget`, no request errors).
3. Performance load gate (full) passed with no failed profiles.
4. Failure recovery gate passed with no failed checks.
5. Evidence artifacts are less than 24 hours old.
6. CI run containing these artifacts is green on `main` or release candidate branch.
7. Operations control-plane endpoints are reachable and token-guarded.
8. No unresolved Sev-1/Sev-2 production-readiness defects.

## Interpretation Guidance
1. If smoke fails:
- treat as hard blocker.
2. If latency fails:
- profile endpoint outliers and rebalance budgets before sign-off.
3. If full load gate fails:
- inspect failed profile(s), backlog drain behavior, and pressure metrics.
4. If failure recovery fails:
- do not proceed; fix recovery determinism first.

## Escalation Rules
1. Any hard gate failure blocks release.
2. Re-run failing gate after fix and regenerate sign-off pack.
3. Attach both failed and passed artifacts to the incident/change ticket for audit trail.
