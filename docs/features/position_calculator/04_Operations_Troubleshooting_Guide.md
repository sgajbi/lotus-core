# Operations & Troubleshooting Guide: Position Calculator

This guide provides operational instructions for monitoring and troubleshooting the `position_calculator_service`.

## 1. Observability & Monitoring

The health of this service is crucial for both data accuracy and the proper functioning of the reprocessing engine.

### Key Metrics to Watch

| Metric Name | Type | Labels | Description & What to Watch For |
| :--- | :--- | :--- | :--- |
| **`reprocessing_epoch_bumped_total`** | **Counter** | `portfolio_id`, `security_id` | **(New)** Increments every time a back-dated transaction triggers a new epoch and a full reprocessing flow. This is the primary indicator of reprocessing activity. |
| `epoch_mismatch_dropped_total` | Counter | `service_name`, `topic`, `portfolio_id`, `security_id` | Increments every time this consumer discards a Kafka message because its epoch is stale. A high rate indicates that epoch fencing is working correctly to prevent data corruption during an active replay. |
| `event_processing_latency_seconds` | Histogram | `topic`, `consumer_group` | Measures the time taken to process a single transaction. A sudden increase can indicate that the service is recalculating very long position histories, which may be a performance bottleneck. |
| Consumer Lag | Gauge | `topic`, `group_id`, `partition` | High or growing consumer lag on the `transactions.cost.processed` topic is a primary indicator that the service is struggling to keep up with the transaction volume or is stuck in a retry loop. |

## 2. Structured Logging & Tracing

All logs are structured JSON and are tagged with the `correlation_id`. The most important log message from this service is:

* **`"Back-dated transaction detected. Triggering reprocessing flow."`**: This confirms that the service has correctly identified an out-of-order transaction and has initiated the epoch increment and event replay process.

## 3. Common Failure Scenarios & Resolutions

| Scenario | Symptom(s) in API / Logs | Key Log Message(s) / Support API | Resolution / Action |
| :--- | :--- | :--- | :--- |
| **Position History is Incorrect** | Downstream data (e.g., in the `/positions` API) shows wrong quantity or cost basis. | Compare `/positions`, `/position-history`, and `/lineage/.../securities/{security_id}` for the same key/date window. | **Cause:** Upstream `cost_calculator_service` may have published incorrect `net_cost` on the transaction event. <br> **Resolution:** Verify upstream cost basis logic and correlated transaction lineage. |
| **Reprocessing Not Triggered** | A known back-dated transaction was ingested, but epoch state did not advance. | No "Back-dated transaction detected" log message and no change in lineage endpoint epoch/watermark. | **Cause:** Back-dated detection logic did not evaluate to true for the key state. <br> **Resolution:** Validate key lineage via API-first endpoints and escalate with correlation ID plus lineage payloads if logic appears inconsistent. |
| **Messages Sent to DLQ** | The `events_dlqd_total` metric is increasing. | `Unexpected error in position calculator...` | **Cause:** A "poison pill" message caused by a bug in the position calculation logic that isn't handled gracefully. <br> **Resolution:** **Escalate to the development team.** Provide the full DLQ message, which contains the original transaction and a detailed error traceback. |
