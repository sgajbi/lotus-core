# Calculator SLO Baseline Runbook (RFC 065 Phase 0)

## Purpose
Define the minimum operational baseline for calculator throughput and reliability before scaling changes in RFC 065.

## Scope
Per-portfolio operational SLO snapshot for:
1. Valuation calculator
2. Portfolio aggregation (timeseries rollup)
3. Reprocessing key activity

Endpoint:
- `GET /support/portfolios/{portfolio_id}/calculator-slos`

## Response Interpretation
`valuation` and `aggregation` include:
1. `pending_jobs`: queued work not started
2. `processing_jobs`: active work in progress
3. `stale_processing_jobs`: jobs in processing beyond stale threshold
4. `failed_jobs`: terminal failed jobs currently present
5. `failed_jobs_last_24h`: recent fail velocity indicator
6. `oldest_open_job_date`: oldest open job business date
7. `backlog_age_days`: age of backlog against `business_date`

`reprocessing` includes:
1. `active_reprocessing_keys`: number of keys under replay/reprocessing

## Initial SLO Targets (Phase 0 Baseline)
These are baseline targets and should be tuned from production observations.

### Valuation
1. `stale_processing_jobs == 0`
2. `backlog_age_days <= 1` under normal daily flow
3. `failed_jobs_last_24h == 0` for stable periods

### Aggregation
1. `stale_processing_jobs == 0`
2. `backlog_age_days <= 1` under normal daily flow
3. `failed_jobs_last_24h == 0` for stable periods

### Reprocessing
1. `active_reprocessing_keys == 0` outside planned replay windows
2. During replay windows, key count should trend down monotonically

## Alert Thresholds
Set warning/critical thresholds:

1. Warning:
- `valuation.backlog_age_days >= 2`
- `aggregation.backlog_age_days >= 2`
- any `failed_jobs_last_24h > 0`
2. Critical:
- any `stale_processing_jobs > 0`
- `backlog_age_days >= 5`
- `active_reprocessing_keys` increasing for consecutive checks

## Incident Triage Flow
1. Call `/support/portfolios/{portfolio_id}/calculator-slos`.
2. If stale processing > 0:
- inspect `/support/portfolios/{portfolio_id}/valuation-jobs?status=PROCESSING`
- inspect `/support/portfolios/{portfolio_id}/aggregation-jobs?status=PROCESSING`
3. If fail velocity > 0:
- inspect `.../valuation-jobs?status=FAILED` and latest failure reason
- inspect `.../aggregation-jobs?status=FAILED`
4. If backlog age rises:
- verify business date progression
- verify worker availability and consumer lag
- verify no blocking reprocessing floods

## Review Cadence
1. Daily: check critical portfolios
2. Weekly: trend `backlog_age_days` and `failed_jobs_last_24h`
3. Monthly: recalibrate thresholds based on observed load profile

## Notes
1. This runbook is intentionally portfolio-scoped to support targeted investigation.
2. Platform-wide SLO dashboards should aggregate these metrics across portfolios in later RFC 065 phases.
