# Operations & Troubleshooting Guide: Cashflow Processing

This guide provides information for operating and troubleshooting cashflow processing, which runs inside the unified `portfolio_transaction_processing_service` deployment.

## 1. Key Metrics

The service exposes the following critical Prometheus metrics at its `/metrics` endpoint. These should be monitored in a Grafana dashboard.

| Metric Name | Type | Labels | Description |
| :--- | :--- | :--- | :--- |
| `kafka_consumer_events_total` | Counter | `service`, `topic`, `group_id`, `outcome`, `reason` | The activity signal. `BaseConsumer` records every consumer lifecycle and processing event here. Filter on `outcome` and `reason` — there is no `event` label. A flat line under known traffic means the consumer is not progressing. |
| `kafka_consumer_processing_duration_seconds` | Histogram | `service`, `topic`, `group_id` | Per-message processing time. Rising values point at the handler rather than at Kafka. |
| `kafka_consumer_partition_lag_messages` | Gauge | `service`, `topic`, `group_id`, `partition` | Messages between the last committed offset and the cached partition high watermark — the primary backlog signal. |
| `kafka_consumer_in_flight_messages` | Gauge | `service`, `topic`, `group_id` | Messages currently in application processing. With poll-idle, separates a stalled handler from an empty topic. |
| `kafka_consumer_poll_idle_seconds` | Histogram | `service`, `topic`, `group_id` | Poll calls that returned no message. |
| `db_operation_latency_seconds` | Histogram | `repository`, `method` | Measures the latency of database operations. Spikes can indicate DB performance issues. |
| `outbox_events_published_total`| Counter | `aggregate_type`, `topic` | Tracks the number of `CashflowCalculated` events successfully published. |
| **`cashflows_created_total`** | **Counter** | **`classification`, `timing`**| **(New in RFC 022)** Provides a business-level count of generated cashflows. This is crucial for understanding the financial activity being processed (e.g., number of `INCOME` vs. `EXPENSE` flows). |

> **Do not use `kafka_messages_consumed_total` or `kafka_consume_errors_total`.** Both are declared
> in `portfolio_common/monitoring.py`, but the only code that increments them is
> `observe_kafka_consumed` / `observe_kafka_consume_error`, and nothing calls those helpers. A panel
> built on either counter stays at zero whether or not cashflow processing is healthy or failing.

## 2. Common Failure Modes & Recovery

### Symptom: Consumer Lag is Increasing

> Check lag on **all five** consumer groups, not only `portfolio_transaction_processing_group` —
> but read the symptom correctly, because the groups fail differently.
>
> A **missing** cashflow comes from `portfolio_transaction_processing_group`,
> `portfolio_transaction_replay_request_group`, or `corporate_action_manifest_group`. Any of those
> can stall while the others stay current, so the cashflow is never created.
>
> `fixed_income_book_cost_authority_group` and `fixed_income_book_cost_correction_replay_group`
> cannot cause a missing cashflow. They replay already-booked transactions to apply revised
> book-cost authority, and the original cashflow was committed atomically at booking. A stall there
> leaves **stale** values, not absent rows. See
> [the Kafka contract](./02_API_Specification_Cashflow_Calculator.md#21-consumer) for what each
> group carries.

- **Potential Cause 1: Database Performance**
  - **Check**: The `db_operation_latency_seconds` histogram in Grafana. The cashflow *write*
    itself is not instrumented — `SqlAlchemyCashflowRepository.create()` carries no
    `async_timed`, so there is no `method="create_cashflow"` series. Use the timed operations
    that do exist on this path, such as
    `db_operation_latency_seconds{repository="CashflowRulesRepository"}` for rule loads and the
    `CostBasis*` repository operations that share the same unit of work.
  - **Action**: Investigate the database for slow queries, high CPU usage, or connection pool exhaustion.

- **Potential Cause 2: Downstream Outage**
  - **Check**: The `outbox_events_pending` gauge. If this number is high and not decreasing, the outbox dispatcher is failing to publish events. This can be due to Kafka being unavailable.
  - **Action**: Check Kafka broker health and network connectivity from the service.

### Symptom: Messages are ending up in the DLQ

- **Potential Cause 1: Invalid Message Payload**
  - **Check**: The logs for `portfolio_transaction_processing_service`. Look for `ValidationError` or `JSONDecodeError` messages.
  - **Action**: The upstream service is likely publishing a malformed `TransactionEvent`. The message in the DLQ will need to be inspected to identify the schema violation.

- **Potential Cause 2: Missing Cashflow Rule**
  - **Check**: The processing outcome for reason code `cashflow_rule_missing`. This terminal error is emitted when a transaction is received for a type that does not have a corresponding entry in the `cashflow_rules` table.
  - **Action**: This is a configuration error. A business analyst or administrator needs to add a new rule to the `cashflow_rules` table for the missing transaction type. The affected message(s) can then be replayed from the DLQ.
