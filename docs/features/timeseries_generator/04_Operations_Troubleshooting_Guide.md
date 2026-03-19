# Operations & Troubleshooting Guide: Timeseries Generator

This guide provides operational instructions for monitoring and troubleshooting the `timeseries_generator_service`.

## 1. Observability & Monitoring

The health of this service is critical for the availability of all performance and risk analytics.

### Key Metrics to Watch

* **Consumer Lag:** Monitor consumer lag on both primary topics:
  * `valuation.snapshot.persisted`: High lag here indicates the service is failing to generate the base `position_timeseries` records.
  * `portfolio_security_day.position_timeseries.completed`: High lag downstream of this signal usually indicates portfolio aggregation orchestration is stalled in `portfolio_aggregation_service`, not in the position-timeseries worker.
* **`events_dlqd_total` (Counter):** An increase in this metric signifies a "poison pill" message that could not be processed, likely due to a persistent error like a missing FX rate.
* **`event_processing_latency_seconds` (Histogram):** A sudden increase in the latency for the `portfolio_day.aggregation.job.requested` consumer can indicate that it is processing portfolios with a very large number of positions.

## 2. Structured Logging & Tracing

All logs are structured JSON and are tagged with the `correlation_id`. Key log messages can help diagnose issues:

* **`"Processing position snapshot for..."`**: Confirms the `PositionTimeseriesConsumer` is running.
* **`"Scheduler claimed ... jobs for processing"`**: Confirms the `AggregationScheduler` in `portfolio_aggregation_service` is active and dispatching aggregation work.
* **`"Found and claimed ... eligible aggregation jobs"`**: Confirms the portfolio aggregation scheduler in `portfolio_aggregation_service` is claiming portfolio-date jobs.
* **`"Missing FX rate from..."`**: A critical error from the portfolio aggregation logic that will cause the job to fail and the message to be sent to the DLQ.

## 3. Common Failure Scenarios & Resolutions

| Scenario | Symptom(s) in API / Logs | Key Log Message(s) / Support API | Resolution / Action |
| :--- | :--- | :--- | :--- |
| **Incorrect Performance/Risk Figures** | TWR or Risk metrics exposed through the query stack are incorrect (e.g., unexpectedly low market value). | Compare `query_control_plane_service` support APIs such as `/support/portfolios/{portfolio_id}/overview` and `/support/portfolios/{portfolio_id}/aggregation-jobs` against logs. | **Cause:** The portfolio aggregation job may have run on incomplete inputs for a business date. <br> **Resolution:** Use control-plane support APIs to identify pending/failed jobs and replay path, then escalate with correlation IDs and support payloads. |
| **Analytics Data is Stale** | Performance and risk data is not available for the latest business date. | `GET /support/portfolios/{portfolio_id}/aggregation-jobs?status=PROCESSING` or `status=PENDING` returns growing backlog from `query_control_plane_service`. | **Cause:** Scheduler eligibility or upstream data completeness is blocking claims. <br> **Resolution:** Inspect position-timeseries worker and portfolio-aggregation scheduler logs for the affected portfolio and validate lineage progression via control-plane support APIs. |
| **Aggregation Jobs are Failing** | The `events_dlqd_total` metric is increasing for the portfolio aggregation path. | `FxRateNotFoundError` in the logs. | **Cause:** The portfolio aggregation logic requires an FX rate to convert a position's cash flows, but the rate is not in the database for that day. <br> **Resolution:** Ingest the missing FX rate data. Then replay through the supported remediation path rather than assuming the old monolithic timeseries runtime. |

## 4. Gaps and Design Considerations

* **Missing Metrics:** The service lacks specific metrics for its core functions. There is no visibility into how many position vs. portfolio time-series records are created, or how long the portfolio-level aggregation takes. This makes it difficult to diagnose performance issues.
