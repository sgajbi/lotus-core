# Operations & Troubleshooting Guide: Position Processing

This guide provides operational instructions for monitoring and troubleshooting position processing, which runs inside the unified `portfolio_transaction_processing_service` deployment.

## 1. Observability & Monitoring

The health of this service is crucial for both data accuracy and the proper functioning of the reprocessing engine.

### Key Metrics to Watch

| Metric Name | Type | Labels | Description & What to Watch For |
| :--- | :--- | :--- | :--- |
| **`reprocessing_epoch_bumped_total`** | **Counter** | `portfolio_id`, `security_id` | **(New)** Increments every time a back-dated transaction triggers a new epoch and a full reprocessing flow. This is the primary indicator of reprocessing activity. |
| `epoch_mismatch_dropped_total` | Counter | `service_name`, `topic`, `portfolio_id`, `security_id` | Increments every time this consumer discards a Kafka message because its epoch is stale. A high rate indicates that epoch fencing is working correctly to prevent data corruption during an active replay. |
| `lotus_core_transaction_processing_operation_duration_seconds` | Histogram | operation labels | Time to process a single transaction end to end. A sudden increase can mean the runtime is recalculating very long position histories. `event_processing_latency_seconds` is owned by `persistence_service` and is **not** emitted here. |
| Consumer Lag | Gauge | `topic`, `group_id`, `partition` | Alert on the subscriptions that actually drive position effects: `transactions.persisted` (group `portfolio_transaction_processing_group`) and `transactions.reprocessing.requested` (group `portfolio_transaction_replay_request_group`). Growing lag on either indicates the runtime is behind or stuck in a retry loop. Do **not** monitor `transactions.cost.processed` — nothing subscribes to it, so it cannot reveal a stuck worker. |

## 2. Structured Logging & Tracing

All logs are structured JSON and are tagged with the `correlation_id`. The most important log message from this service is:

* **`"Back-dated transaction detected. Advancing position recovery epoch."`**: This confirms that the service identified an out-of-order transaction and initiated an epoch transition. Inspect structured field `backdated_handling`: deployed compatibility consumers use `queue_replay`; the combined atomic path uses `rebuild_inline` and must not depend on the legacy replay topic.

## 3. Common Failure Scenarios & Resolutions

| Scenario | Symptom(s) in API / Logs | Key Log Message(s) / Support API | Resolution / Action |
| :--- | :--- | :--- | :--- |
| **Position History is Incorrect** | Downstream data (e.g., in the `/positions` API) shows wrong quantity or cost basis. | Compare `/positions`, `/position-history`, and `/lineage/.../securities/{security_id}` for the same key/date window. | **Cause:** Cost processing may have staged an incorrect `net_cost` before the position effect was applied. Cost, cashflow, and position effects complete in one atomic use case, so check the transaction's cost-basis evidence rather than a separate upstream deployment. <br> **Resolution:** Verify cost basis logic and correlated transaction lineage. |
| **Reprocessing Not Triggered** | A known back-dated transaction was ingested, but epoch state did not advance. | No "Back-dated transaction detected" log message and no change in lineage endpoint epoch/watermark. | **Cause:** Back-dated detection logic did not evaluate to true for the key state. <br> **Resolution:** Validate key lineage via API-first endpoints and escalate with correlation ID plus lineage payloads if logic appears inconsistent. |
| **Messages Sent to DLQ** | Depth is growing on the shared `dlq.persistence_service` topic. This runtime emits no DLQ counter of its own; `events_dlqd_total` belongs to `persistence_service`. | `Unexpected error...` in the transaction-processing logs | **Cause:** A "poison pill" message caused by a bug in the position calculation logic that isn't handled gracefully. <br> **Resolution:** **Escalate to the development team.** Provide the full DLQ message, which contains the original transaction and a detailed error traceback. |
