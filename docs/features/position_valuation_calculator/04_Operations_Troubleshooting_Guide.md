# Operations & Troubleshooting Guide: Position Valuation Calculator

This guide provides operational instructions for monitoring and troubleshooting the `position-valuation-calculator` service.

## 1. Observability & Monitoring

The health of this service is critical for overall data freshness. Monitor the following Prometheus metrics.

### Key Metrics to Watch

These metrics are declared in shared `portfolio_common/monitoring.py`, but each is updated by
exactly one service. **Three of the five are never updated by this service**, so scraping only the
calculator's endpoint shows no scheduler backlog even while the orchestrator is degraded. Scrape
both, or alert on the orchestrator for its own series.

| Metric Name | Type | Labels | Updated by | Description & What to Watch For |
| :--- | :--- | :--- | :--- | :--- |
| **`position_state_watermark_lag_days`** | **Gauge** | - | `valuation_orchestrator_service` | Most recently observed data freshness lag in days for a key being processed by the scheduler. Use `scheduler_gap_days` for aggregate distribution alerting and support APIs/logs for portfolio/security drilldown. |
| `scheduler_gap_days` | Histogram | - | `valuation_orchestrator_service` | Distribution of gaps in days between a position's watermark and the current business date. Good for overall backlog health. |
| `valuation_jobs_created_total` | Counter | `job_type` | `valuation_orchestrator_service` | Increments when the scheduler stages valuation jobs. Use the `backfill` job type for scheduler-created backfill pressure. |
| `valuation_jobs_skipped_total` | Counter | `reason` | **this service** | Increments when a consumer skips a valuation job. `no_position_history` is often normal for jobs created at the beginning of a position's life. |
| `valuation_jobs_failed_total` | Counter | `reason` | **this service** | Increments when a consumer permanently fails a job due to missing reference data, missing FX, or valuation calculation failure. Any increase requires investigation through support APIs and correlated logs. |

The first three are updated from `valuation_orchestrator_service/app/core/valuation_backfill_planner.py`.


## 2. Structured Logging & Tracing

All logs are structured JSON and tagged with a `correlation_id`. Key log messages can help diagnose issues:

**Two services are involved.** Lines below marked *(orchestrator)* are emitted by `valuation_orchestrator_service`. Treat the marking as a guide, not a guarantee: several of these messages originate in shared `portfolio-common` code and are attributed by whichever service calls it. Collect both services' logs when tracing a valuation problem end to end.

* **`"Effective-dated price requires durable reprocessing."`** *(orchestrator)*: Emitted by `PriceEventConsumer` in `valuation_orchestrator_service` when an effective-dated price needs a durable reprocessing trigger. Its receipt-side counterpart is `"Received new market price for ... on ..."`, and `"Queued immediate valuation jobs for market price event."` covers the in-horizon path. Search that service's logs, not this one's.
* **Price-before-position-history race**: no stable log literal to grep for. When a price arrives before any open position key exists, the orchestrator persists a durable replay trigger rather than losing the valuation opportunity; confirm it through a row in `instrument_reprocessing_state` for the security, not through a log message.
* **Watermark advance** *(orchestrator)*: no stable log literal to grep for. Confirm progress through `position_state_watermark_lag_days` falling and the support APIs, rather than a message. `"ValuationScheduler normalized no-history states to current watermark."` covers only the no-history case.
* **`"Backfill valuation jobs staged in bounded chunk."`** *(orchestrator)*: Confirms the scheduler identified data gaps and staged work. Its planning-side counterpart is `"Backfill valuation jobs planned for state."`, and `"Scheduler: No keys need backfilling."` means there was nothing to do.
* **`"Skipping job due to missing position data..."`**: A common warning from this service's `ValuationConsumer`. Expected when the orchestrator creates a job for a date before the first transaction.
* **`"Reset ... stale valuation jobs from 'PROCESSING' to 'PENDING'"`** *(orchestrator)*: The scheduler's self-healing mechanism recovered jobs from a potentially crashed consumer. `ValuationScheduler._reset_stale_valuation_jobs` drives `ValuationStaleJobResetter`, and the warning text itself comes from shared `portfolio_common/valuation_repository_base.py`, so search the orchestrator's logs for it, not the compute worker's.

## 3. Common Failure Scenarios & Resolutions

| Scenario | Symptom(s) | Key Log Message(s) / Support API | Resolution / Action |
| :--- | :--- | :--- | :--- |
| **Positions Not Valued** | Data in the query APIs is stale. `scheduler_gap_days` shows elevated backlog distribution or `position_state_watermark_lag_days` remains high. | `GET /support/portfolios/{portfolio_id}/valuation-jobs?status_filter=PENDING` shows growing pending jobs. | **Cause:** `ValuationScheduler` in `valuation_orchestrator_service` may not be dispatching jobs, or this service's `ValuationConsumer` workers may be stalled. <br> **Resolution:** Check the orchestrator's scheduler logs and this service's consumer logs. Correlate with `GET /support/portfolios/{portfolio_id}/overview`. |
| **Valuations Failing** | The `valuation_jobs_failed_total` metric is increasing. | `GET /support/portfolios/{portfolio_id}/valuation-jobs?status_filter=FAILED` contains failure reasons. | **Cause:** Most commonly missing reference data (FX rate or market price). <br> **Resolution:** Ingest missing data and trigger controlled replay/reprocessing for affected keys. |
| **Back-dated Price Ignored** | A back-dated price was ingested, but old position values remain unchanged. | No `Effective-dated price requires durable reprocessing.` message in `valuation_orchestrator_service`. The `instrument_reprocessing_state` table is empty for the security. | **Cause:** `PriceEventConsumer` might be down or failing. It runs in `valuation_orchestrator_service`. <br> **Resolution:** Check that service's logs and health, not the calculator's. |
| **Quiet-Day Timeseries Row Missing After Price Ingestion** | A position exists on day N and day N+1 market prices are present, but analytics only returns the cash leg or an incomplete security set for day N+1. | There is no log literal for this path. Look for missing or stale rows in `instrument_reprocessing_state` / support lineage views for the affected security and date. | **Cause:** A price arrived before the corresponding open position key was visible, and the durable replay trigger did not get drained. <br> **Resolution:** Verify `instrument_reprocessing_state` and `reprocessing_jobs` are clearing, then inspect scheduler logs for watermark reset fan-out and valuation job creation for the affected security/date. |
