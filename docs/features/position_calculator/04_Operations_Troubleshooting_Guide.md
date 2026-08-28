# Operations & Troubleshooting Guide: Position Processing

This guide provides operational instructions for monitoring and troubleshooting position processing, which runs inside the unified `portfolio_transaction_processing_service` deployment.

## 1. Observability & Monitoring

The health of this service is crucial for both data accuracy and the proper functioning of the reprocessing engine.

### Key Metrics to Watch

| Metric Name | Type | Labels | Description & What to Watch For |
| :--- | :--- | :--- | :--- |
| **`reprocessing_epoch_bumped_total`** | **Counter** | `trigger` | Increments every time a back-dated transaction triggers a new epoch and a reprocessing flow. The primary indicator of reprocessing activity. It carries only `trigger` — there is no per-portfolio or per-security label, so use support APIs and lineage views for key-level drilldown. |
| `epoch_mismatch_dropped_total` | Counter | `service_name`, `topic` | Increments every time this consumer discards a Kafka message because its epoch is stale. A high rate indicates epoch fencing is working correctly during an active replay. It carries no portfolio or security label; drill down through support APIs rather than PromQL. |
| `lotus_core_transaction_processing_operation_duration_seconds` | Histogram | `stage`, `outcome` | Duration per processing **stage**, not per transaction. `ProcessTransactionUseCase` records separate observations for `transaction`, `idempotency`, `cost`, `cashflow`, `position`, `pipeline`, `commit`, and `replay`, so aggregating without a selector mixes nested stages and can hide slow transactions. Use `stage="transaction"` for the end-to-end signal and `stage="position"` to isolate position work. `event_processing_latency_seconds` is owned by `persistence_service` and is **not** emitted here. |
| Consumer Lag | Gauge | `service`, `topic`, `group_id`, `partition` | Alert on **all five** consumer groups, not just the two that process transactions directly. `portfolio_transaction_processing_group` and `portfolio_transaction_replay_request_group` drive position effects directly. `corporate_action_manifest_group`, `fixed_income_book_cost_authority_group`, and `fixed_income_book_cost_correction_replay_group` stage work that reaches position processing on a later hop — a stall on any of them leaves position state silently wrong while the two direct groups show no lag. Do **not** monitor `transactions.cost.processed`; nothing subscribes to it, so it cannot reveal a stuck worker. |

## 2. Structured Logging & Tracing

All logs are structured JSON and are tagged with the `correlation_id`. The most important log message from this service is:

* **`"Back-dated transaction detected. Advancing position recovery epoch."`**: This confirms that the service identified an out-of-order transaction and initiated an epoch transition. Inspect structured field `backdated_handling`. The unified runtime emits exactly one value, **`inline_rebuild`** (`PrometheusPositionHistoryObserver.backdated_recalculation_detected()`). Neither `queue_replay` nor `rebuild_inline` is emitted anywhere — filtering on either matches nothing and hides every rebuild. The same log line also carries `effective_completed_date`, `watermark_date`, `latest_position_history_date`, and `current_epoch`, which together show why the rebuild was triggered.

## 3. Common Failure Scenarios & Resolutions

| Scenario | Symptom(s) in API / Logs | Key Log Message(s) / Support API | Resolution / Action |
| :--- | :--- | :--- | :--- |
| **Position History is Incorrect** | Downstream data (e.g., in the `/positions` API) shows wrong quantity or cost basis. | Compare `/positions`, `/position-history`, and `/lineage/.../securities/{security_id}` for the same key/date window. | **Cause:** Cost processing may have staged an incorrect `net_cost` before the position effect was applied. Cost, cashflow, and position effects complete in one atomic use case, so check the transaction's cost-basis evidence rather than a separate upstream deployment. <br> **Resolution:** Verify cost basis logic and correlated transaction lineage. |
| **Reprocessing Not Triggered** | A known back-dated transaction was ingested, but epoch state did not advance. | No "Back-dated transaction detected" log message and no change in lineage endpoint epoch/watermark. | **Cause:** Back-dated detection logic did not evaluate to true for the key state. <br> **Resolution:** Validate key lineage via API-first endpoints and escalate with correlation ID plus lineage payloads if logic appears inconsistent. |
| **Messages Sent to DLQ** | Depth is growing on the shared `dlq.persistence_service` topic. This runtime emits no DLQ counter of its own; `events_dlqd_total` belongs to `persistence_service`. | `kafka.consumer.processing_terminal` / `Kafka message processing failed terminally.` followed by `kafka.consumer.dlq_published` / `Kafka message published to DLQ.` in the transaction-processing logs | **Cause:** A "poison pill" message caused by a bug in the position calculation logic that isn't handled gracefully. <br> **Resolution:** **Escalate to the development team.** Provide the full DLQ message, which contains the original transaction and a detailed error traceback. |
