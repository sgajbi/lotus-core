# Institutional Sign-Off Runbook

## Purpose
Provide a deterministic, auditable sign-off flow for institutional readiness before go-live.

## Required Evidence Inputs
Evidence must come from the latest generated artifacts in `output/task-runs`:
1. `*-docker-endpoint-smoke.json`
2. `*-latency-profile.json`
3. `*-performance-load-gate.json` (full tier)
4. `*-failure-recovery-gate.json`
5. `*-bank-day-load-reconciliation.json` (prefer exhaustive portfolio coverage when both exhaustive and sampled artifacts exist)

## Generate Sign-Off Pack
Run:

```powershell
make test-institutional-signoff-pack
```

This command writes:
1. `output/task-runs/*-institutional-signoff-pack.json`
2. `output/task-runs/*-institutional-signoff-pack.md`

To generate the full RFC-086 completion evidence set first, run:

```powershell
make test-institutional-completion-gate
```

That governed wrapper runs the bank-day load scenario and then exhaustive
reconciliation for the exact generated `run_id`, producing both:
1. `output/task-runs/*-bank-day-load.json|md`
2. `output/task-runs/*-bank-day-load-reconciliation.json|md`

## CI Enforcement
1. GitHub Actions job `Institutional Sign-Off Pack` runs on:
   1. `main` pushes,
   2. scheduled pipelines,
   3. manual workflow dispatch.
2. The job is a required production-readiness gate and fails when:
   1. any required artifact is missing,
   2. any gate status is failed,
   3. any required artifact is older than 24 hours (`--max-age-hours 24`).
3. The main releasability workflow now generates RFC-086 completion evidence through
   `Main Releasability / Institutional Completion Gate` before sign-off aggregation.

## Go-Live Checklist
All items must be `yes`:
1. Docker endpoint smoke passed.
2. Latency profile has zero endpoint violations (`p95 <= budget`, no request errors).
3. Performance load gate (full) passed with no failed profiles.
4. Failure recovery gate passed with no failed checks.
5. Bank-day load reconciliation proves complete portfolio coverage, reconciled sampled or exhaustive tie-out, and bounded completion lag.
6. Evidence artifacts are less than 24 hours old.
7. CI run containing these artifacts is green on `main` or release candidate branch.
8. Operations control-plane endpoints are reachable and token-guarded.
9. No unresolved Sev-1/Sev-2 production-readiness defects.

## Interpretation Guidance
1. If smoke fails:
- treat as hard blocker.
2. If latency fails:
- profile endpoint outliers and rebalance budgets before sign-off.
3. If full load gate fails:
- inspect failed profile(s), backlog drain behavior, and pressure metrics.
4. If failure recovery fails:
- do not proceed; fix recovery determinism first.
5. If reconciliation fails:
- treat incomplete portfolio breadth, sampled or exhaustive mismatch, or excessive post-snapshot completion lag as release blockers.
6. When both lightweight and approval-grade artifacts exist:
- sign-off must use the strongest available evidence, not merely the newest artifact.
- for performance load, prefer `full` profile-tier artifacts over newer `fast` artifacts.
- for bank-day reconciliation, prefer exhaustive artifacts where `portfolio_count_evaluated == portfolios_ingested` over newer sampled refresh artifacts.

## Escalation Rules
1. Any hard gate failure blocks release.
2. Re-run failing gate after fix and regenerate sign-off pack.
3. Attach both failed and passed artifacts to the incident/change ticket for audit trail.
