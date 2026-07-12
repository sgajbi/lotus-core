# CR-167 Replay No-Op Dashboard Signal Review

## Scope
- Replay and recovery observability
- Grafana operational dashboard
- Operator guide coverage

## Finding
`reprocessing_worker_jobs_noop_total{job_type, reason}` had been added to the runtime path for `RESET_WATERMARKS` jobs that legitimately found no impacted portfolios. The signal existed in Prometheus, but the main Grafana dashboard did not surface it and the operator guide did not explain how to interpret it.

## Why It Matters
A no-op replay outcome is materially different from a failure. Operators need to distinguish:
- healthy completion with no impacted portfolios
- stale-skip pressure
- real replay failure or backlog growth

Without dashboard and guide coverage, the metric is easy to miss and replay triage stays unnecessarily log-driven.

## Change
- Added `rate(reprocessing_worker_jobs_noop_total[5m])` to the `Reprocessing Worker Throughput and Backlog` panel, split by `job_type` and `reason`.
- Updated the Grafana guide to explain how to use the new line when replay or reprocessing appears stuck.

## Outcome
Replay no-op outcomes are now visible to operators in the same section as replay claim/completion/failure pressure, so the signal is actionable instead of hidden.

## Evidence
- `grafana/dashboards/portfolio_analytics.json`
- `docs/operations/Grafana-Dashboard-Guide.md`
- `src/libs/portfolio-common/portfolio_common/monitoring.py`
- `src/services/valuation_orchestrator_service/app/core/reprocessing_worker.py`
