# Operations & Troubleshooting Guide: Cost Calculator

This guide provides operational instructions for monitoring and troubleshooting the `cost_calculator_service`.

## 1. Observability & Monitoring

The service is a standard Kafka consumer and exposes metrics via its `/metrics` endpoint.

### Key Metrics to Watch

* **Consumer Lag**: The most critical metric for any consumer. High or growing consumer lag on the `raw_transactions_completed` topic indicates that the service cannot keep up with the volume of incoming transactions. This could be due to a performance bottleneck or a persistent error causing messages to be retried.
* **`events_processed_total` (Counter)**: Tracks the number of transactions successfully processed. A flat line on this metric when there is known traffic indicates the service is stuck or failing.
* **`events_dlqd_total` (Counter)**: Tracks the number of messages sent to the Dead-Letter Queue. Any increase in this metric requires immediate investigation, as it signifies a "poison pill" message that could not be processed.
* **`recalculation_depth` (Histogram)**: **(NEW)** Tracks the number of historical transactions fetched and replayed for each incoming event. High values in the upper buckets (e.g., >500) indicate that transactions are frequently affecting positions with very long histories, which can be a source of latency.
* **`recalculation_duration_seconds` (Histogram)**: **(NEW)** Measures the wall-clock time spent inside the core financial engine's recalculation process. This isolates the performance of the financial logic from Kafka and database I/O. A spike in this metric points directly to a performance bottleneck in the calculation engine itself.
* **`event_processing_latency_seconds` (Histogram)**: Measures the total time taken to process a single transaction, including all I/O. A sudden increase can indicate a performance issue, often related to fetching a long transaction history from the database for recalculation.

## 2. Structured Logging & Tracing

All logs are structured JSON and are tagged with the `correlation_id` of the original ingestion request. When investigating a problematic transaction, use its `transaction_id` or `portfolio_id` to find the relevant `correlation_id` in the logs, which can then be used to trace the entire calculation process.

## 3. Common Failure Scenarios & Resolutions

| Scenario                  | Symptom(s) in API / Logs                                                                            | Key Log Message(s) / Metric Alert                                  | Resolution / Action                                                                                                                                                                                                                                                                                                                                                                                                                       |
| :------------------------ | :-------------------------------------------------------------------------------------------------- | :----------------------------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Incorrect Realized P&L** | Downstream reports show incorrect P&L. A transaction's `realized_gain_loss` field in the database is wrong. | `FxRateNotFoundError` in service logs.                             | **Cause:** The most common cause is a missing or incorrect FX rate in the database for either the BUY or SELL date of a dual-currency trade. <br> **Resolution:** Ingest the correct historical FX rate. The service has a built-in retry mechanism for this, but if the data is permanently missing, the message will eventually go to the DLQ. After fixing the data, the message must be replayed from the DLQ.                               |
| **Messages Sent to DLQ** | The `events_dlqd_total` metric is increasing.                                                       | `Unexpected error processing transaction... Sending to DLQ.`       | **Cause:** This indicates a "poison pill" message, likely caused by a bug in the service-owned cost engine or an unexpected data shape that the logic cannot handle (e.g., a `TRANSFER_OUT` for a security with no prior cost basis). <br> **Resolution:** **Escalate to the development team.** Provide the full DLQ message from Kafka, which contains the original message and a detailed error traceback.                     |
| **High Consumer Lag** | Kafka consumer lag for the `cost_calculator_group` is high and growing.                               | `DB or data availability error; will retry...` appears frequently in logs. `recalculation_duration_seconds` shows high latency. | **Cause:** The service is stuck in a retry loop, often due to a transient database issue or a data dependency problem (like a missing portfolio). It could also indicate a performance bottleneck where individual recalculations for positions with very long histories are taking too long. <br> **Resolution:** Check database health and the logs for the root cause of the retries. Use the new metrics to diagnose performance issues. |
