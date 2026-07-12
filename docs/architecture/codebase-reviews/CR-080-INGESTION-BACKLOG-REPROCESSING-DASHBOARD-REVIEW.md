# CR-080 Ingestion Backlog and Reprocessing Dashboard Review

## Scope
- `grafana/dashboards/portfolio_analytics.json`
- `src/libs/portfolio-common/portfolio_common/monitoring.py`
- existing producers of ingestion backlog and reprocessing worker metrics

## Finding
The platform already exported two important ingestion-reliability signals:

- `ingestion_backlog_age_seconds`
- `reprocessing_active_keys_total`

It also exported the reprocessing worker throughput counters:

- `reprocessing_worker_jobs_claimed_total`
- `reprocessing_worker_jobs_completed_total`
- `reprocessing_worker_jobs_failed_total`

Those metrics were not surfaced in the bundled Grafana dashboard. Operators therefore had to pivot to raw Prometheus queries or APIs to understand whether ingestion delay or replay pressure was building, even though the data was already available.

## Change
Added two Grafana panels to the main portfolio analytics dashboard:

1. `Ingestion Backlog and Active Reprocessing`
2. `Reprocessing Worker Throughput and Failures`

The first panel gives direct visibility into backlog age and how many `(portfolio, security)` keys are actively in `REPROCESSING`. The second exposes claim/completion/failure rate by `job_type`, which makes replay pressure and worker health visible without leaving the dashboard.

## Why this is the right fix
- no new metric contract was needed
- no runtime behavior changed
- operator visibility improved immediately
- the change is low-risk and consistent with CR-074, CR-078, and CR-079

## Residual follow-up
- If operators need a single ingestion recovery dashboard later, combine backlog, replay, DLQ, and worker throughput into a dedicated recovery view instead of overloading the overview dashboard indefinitely.
- If per-portfolio or per-security reprocessing visibility is needed, add focused control-plane panels rather than high-cardinality Prometheus labels.

## Evidence
- `grafana/dashboards/portfolio_analytics.json`
- `src/libs/portfolio-common/portfolio_common/monitoring.py`
