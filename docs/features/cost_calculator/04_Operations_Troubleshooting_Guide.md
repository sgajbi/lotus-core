# Operations & Troubleshooting Guide: Cost Processing

This guide provides operational instructions for monitoring and troubleshooting cost processing, which runs inside the unified `portfolio_transaction_processing_service` deployment.

## 1. Observability & Monitoring

The service is a standard Kafka consumer and exposes metrics via its `/metrics` endpoint.

### Key Metrics to Watch

* **Consumer Lag**: The most critical metric for any consumer. High or growing consumer lag on the `transactions.persisted` topic indicates that the service cannot keep up with the volume of incoming transactions. This could be due to a performance bottleneck or a persistent error causing messages to be retried.
These are the instruments the unified runtime actually emits, from
`app/infrastructure/cost_basis/metrics.py` and the transaction-processing runtime:

* **`lotus_core_transaction_processing_operations_total` (Counter)**: Transaction-processing operations. A flat line under known traffic means the runtime is stuck or failing.
* **`lotus_core_transaction_processing_operation_duration_seconds` (Histogram)**: End-to-end time for a processing operation, including I/O. Use it for overall latency.
* **`recalculation_duration_seconds` (Histogram)**: Wall-clock time inside the cost recalculation itself, isolating financial logic from Kafka and database I/O. A spike here points at the calculation path rather than infrastructure.
* **`recalculation_depth` (Histogram)**: Historical transactions replayed per incoming event. High upper buckets (>500) mean transactions frequently hit positions with long histories, a latency source.
* **`cost_processing_execution_total` (Counter)**: Cost-processing executions.
* **`cost_processing_open_lots_restored` (Histogram)**: Open lots restored during processing.

**Do not build dashboards on `events_processed_total`, `events_dlqd_total`, or
`event_processing_latency_seconds` for this service.** `SERVICE_LOCAL_METRIC_OWNERS` in
`portfolio_common/observability_contracts.py` assigns all three to `persistence_service`, and the
unified runtime never emits them, so a panel built on them stays empty while the service it is
supposed to watch degrades.

DLQ volume is likewise not exposed as a metric by this runtime. All five of its consumers route
failures to the shared `dlq.persistence_service` topic; observe DLQ depth on that topic rather than
through a service-local counter.

## 2. Structured Logging & Tracing

All logs are structured JSON and are tagged with the `correlation_id` of the original ingestion request. When investigating a problematic transaction, use its `transaction_id` or `portfolio_id` to find the relevant `correlation_id` in the logs, which can then be used to trace the entire calculation process.

## 3. Common Failure Scenarios & Resolutions

| Scenario                  | Symptom(s) in API / Logs                                                                            | Key Log Message(s) / Metric Alert                                  | Resolution / Action                                                                                                                                                                                                                                                                                                                                                                                                                       |
| :------------------------ | :-------------------------------------------------------------------------------------------------- | :----------------------------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Incorrect Realized P&L** | Downstream reports show incorrect P&L. A transaction's `realized_gain_loss` field in the database is wrong. | `FxRateNotFoundError` in service logs.                             | **Cause:** The most common cause is a missing or incorrect FX rate in the database for either the BUY or SELL date of a dual-currency trade. <br> **Resolution:** Ingest the correct historical FX rate. The service has a built-in retry mechanism for this, but if the data is permanently missing, the message will eventually go to the DLQ. After fixing the data, the message must be replayed from the DLQ.                               |
| **Messages Sent to DLQ** | Depth is growing on the shared `dlq.persistence_service` topic.                                                       | `kafka.consumer.dlq_published` / `Kafka message published to DLQ.` (preceded by `Kafka retryable message failure budget exhausted; routing message to DLQ.` when retries were exhausted)       | **Cause:** This indicates a "poison pill" message, likely caused by a bug in the service-owned cost engine or an unexpected data shape that the logic cannot handle (e.g., a `TRANSFER_OUT` for a security with no prior cost basis). <br> **Resolution:** **Escalate to the development team.** Provide the full DLQ message from Kafka, which contains the original message and a detailed error traceback.                     |
| **High Consumer Lag** | Kafka consumer lag for the `portfolio_transaction_processing_group` is high and growing.                               | `kafka.consumer.processing_retryable` / `Kafka message processing failed retryably; ordered retry scheduled.` appears frequently in logs. `recalculation_duration_seconds` shows high latency. | **Cause:** The service is stuck in a retry loop, often due to a transient database issue or a data dependency problem (like a missing portfolio). It could also indicate a performance bottleneck where individual recalculations for positions with very long histories are taking too long. <br> **Resolution:** Check database health and the logs for the root cause of the retries. Use the new metrics to diagnose performance issues. |
