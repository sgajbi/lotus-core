# Operations & Troubleshooting Guide: Position Valuation Calculator

This guide provides operational instructions for monitoring and troubleshooting the `position-valuation-calculator` service.

## 1. Observability & Monitoring

The health of this service is critical for overall data freshness. Monitor the following Prometheus metrics.

### Key Metrics to Watch

| Metric Name | Type | Labels | Description & What to Watch For |
| :--- | :--- | :--- | :--- |
| **`position_state_watermark_lag_days`** | **Gauge** | `portfolio_id`, `security_id` | **(New)** Tracks the current data freshness lag in days for each key being processed by the scheduler. Ideal for creating precise alerts (e.g., `ALERT if lag > 2 days`). |
| `scheduler_gap_days` | Histogram | - | Measures the distribution of gaps in days between a position's watermark and the current business date. Good for observing the overall health and backlog of the system. |
| `valuation_jobs_skipped_total` | Counter | `portfolio_id`, `security_id` | Increments when a consumer skips a valuation job because no position history was found for the given date. This is often normal behavior for jobs created at the very beginning of a position's life. |
| `valuation_jobs_failed_total` | Counter | `portfolio_id`, `security_id`, `reason` | Increments when a consumer permanently fails a job due to missing reference data (e.g., an instrument or FX rate). Any increase in this metric requires investigation. |


## 2. Structured Logging & Tracing

All logs are structured JSON and tagged with a `correlation_id`. Key log messages can help diagnose issues:

* **`"Back-dated price event detected..."`**: Confirms that the `PriceEventConsumer` has correctly identified a back-dated price and will trigger a reprocessing flow.
* **`"No open position keys were ready for in-horizon market price..."`**: Confirms that the service detected the price-before-position-history race and persisted a durable replay trigger instead of losing the valuation opportunity.
* **`"ValuationScheduler: advanced N watermarks..."`**: **(New)** High-visibility log proving that the scheduler is successfully advancing watermarks for completed keys.
* **`"Created ... backfill valuation jobs for ..."`**: Confirms that the `ValuationScheduler` is correctly identifying data gaps and creating work.
* **`"Skipping job due to missing position data..."`**: A common warning from the `ValuationConsumer`. This is expected if the scheduler creates a job for a date before the first transaction.
* **`"Reset ... stale valuation jobs from 'PROCESSING' to 'PENDING'"`**: This message indicates that the scheduler's self-healing mechanism has activated to recover jobs from a potentially crashed consumer.

## 3. Common Failure Scenarios & Resolutions

| Scenario | Symptom(s) | Key Log Message(s) / Support API | Resolution / Action |
| :--- | :--- | :--- | :--- |
| **Positions Not Valued** | Data in the query APIs is stale. `position_state_watermark_lag_days` gauge shows high values for some keys. | `GET /support/portfolios/{portfolio_id}/valuation-jobs?status_filter=PENDING` shows growing pending jobs. | **Cause:** The `ValuationScheduler` may not be dispatching jobs, or consumers may be stalled. <br> **Resolution:** Check scheduler and consumer logs. Correlate with `GET /support/portfolios/{portfolio_id}/overview`. |
| **Valuations Failing** | The `valuation_jobs_failed_total` metric is increasing. | `GET /support/portfolios/{portfolio_id}/valuation-jobs?status_filter=FAILED` contains failure reasons. | **Cause:** Most commonly missing reference data (FX rate or market price). <br> **Resolution:** Ingest missing data and trigger controlled replay/reprocessing for affected keys. |
| **Back-dated Price Ignored** | A back-dated price was ingested, but old position values remain unchanged. | No `Back-dated price event detected` log message. The `instrument_reprocessing_state` table is empty for the security. | **Cause:** The `PriceEventConsumer` might be down or failing. <br> **Resolution:** Check the logs for the `position-valuation-calculator`. If there are no obvious errors, restart the service to ensure the consumer is running correctly. |
| **Quiet-Day Timeseries Row Missing After Price Ingestion** | A position exists on day N and day N+1 market prices are present, but analytics only returns the cash leg or an incomplete security set for day N+1. | Look for `No open position keys were ready for in-horizon market price...` followed by missing or stale rows in `instrument_reprocessing_state` / support lineage views. | **Cause:** A price arrived before the corresponding open position key was visible, and the durable replay trigger did not get drained. <br> **Resolution:** Verify `instrument_reprocessing_state` and `reprocessing_jobs` are clearing, then inspect scheduler logs for watermark reset fan-out and valuation job creation for the affected security/date. |
