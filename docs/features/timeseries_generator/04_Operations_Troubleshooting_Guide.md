# Operations & Troubleshooting Guide: Timeseries Generator

This guide provides operational instructions for monitoring and troubleshooting the `timeseries_generator_service`.

## 1. Observability & Monitoring

The health of this service is critical for the availability of all performance and risk analytics.

### Key Metrics to Watch

* **Consumer Lag:** Monitor consumer lag on both primary topics:
  * `valuation.snapshot.persisted`: High lag here indicates the service is failing to generate the base `position_timeseries` records.
  * `portfolio_day.aggregation.job.requested`: High lag here indicates portfolio aggregation orchestration or consumption is stalled in `portfolio_aggregation_service`.
* **`events_dlqd_total` (Counter):** An increase means the delivery was malformed or the application could not durably record its failure. Missing governed source data normally leaves the aggregation job in `FAILED` for support-led remediation rather than duplicating failure evidence in the DLQ.
* **`event_processing_latency_seconds` (Histogram):** A sudden increase in the latency for the `portfolio_day.aggregation.job.requested` consumer can indicate that it is processing portfolios with a very large number of positions.

## 2. Structured Logging & Tracing

All logs are structured JSON and are tagged with the `correlation_id`. Key log messages can help diagnose issues:

* **`"Position-timeseries materialization completed."`**: Confirms the position-timeseries application use case finished and reports whether current or dependent days changed.
* **`"Scheduler claimed ... jobs for processing"`**: Confirms the `AggregationScheduler` in `portfolio_aggregation_service` is active and dispatching aggregation work.
* **`"Found and claimed ... eligible aggregation jobs"`**: Confirms the portfolio aggregation scheduler in `portfolio_aggregation_service` is claiming portfolio-date jobs.
* **`"Missing FX rate from..."`**: A critical source-data error that causes the owned aggregation job to fail without publishing partial output.
* **`"Portfolio aggregation requires instrument reference data."`**: A position could not be tied to authoritative instrument metadata, so Core rejected the incomplete portfolio aggregate and failed the owned job.

## 3. Common Failure Scenarios & Resolutions

| Scenario | Symptom(s) in API / Logs | Key Log Message(s) / Support API | Resolution / Action |
| :--- | :--- | :--- | :--- |
| **Incorrect Performance/Risk Figures** | TWR or Risk metrics exposed through the query stack are incorrect (e.g., unexpectedly low market value). | Compare `query_control_plane_service` support APIs such as `/support/portfolios/{portfolio_id}/overview` and `/support/portfolios/{portfolio_id}/aggregation-jobs` against logs. | **Cause:** The portfolio aggregation job may have run on incomplete inputs for a business date. <br> **Resolution:** Use control-plane support APIs to identify pending/failed jobs and replay path, then escalate with correlation IDs and support payloads. |
| **Analytics Data is Stale** | Performance and risk data is not available for the latest business date. | `GET /support/portfolios/{portfolio_id}/aggregation-jobs?status=PROCESSING` or `status=PENDING` returns growing backlog from `query_control_plane_service`. | **Cause:** Scheduler eligibility or upstream data completeness is blocking claims. <br> **Resolution:** Inspect position-timeseries worker and portfolio-aggregation scheduler logs for the affected portfolio and validate lineage progression via control-plane support APIs. |
| **Aggregation Jobs are Failing** | The support API reports `FAILED` aggregation jobs; DLQ growth occurs only when delivery validation or failure persistence also fails. | `FxRateNotFoundError`, `InstrumentReferenceNotFoundError`, or `Portfolio-timeseries materialization failed; marking the owned job failed.` | **Cause:** Required FX or instrument reference data is absent/invalid, or another calculation dependency failed. Core does not publish a partial portfolio aggregate. <br> **Resolution:** Correct the governed reference data, confirm position-timeseries completeness, and replay through the supported remediation path with the original correlation evidence. |

## 4. Gaps and Design Considerations

* **Missing Metrics:** The service lacks specific metrics for its core functions. There is no visibility into how many position vs. portfolio time-series records are created, or how long the portfolio-level aggregation takes. This makes it difficult to diagnose performance issues.
