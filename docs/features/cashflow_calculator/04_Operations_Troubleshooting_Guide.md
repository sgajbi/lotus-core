# Operations & Troubleshooting Guide: Cashflow Calculator

This guide provides information for operating and troubleshooting the `cashflow_calculator_service`.

## 1. Key Metrics

The service exposes the following critical Prometheus metrics at its `/metrics` endpoint. These should be monitored in a Grafana dashboard.

| Metric Name | Type | Labels | Description |
| :--- | :--- | :--- | :--- |
| `kafka_messages_consumed_total`| Counter | `topic`, `group_id` | Tracks the total number of messages consumed from Kafka. A healthy service shows this steadily increasing. |
| `kafka_consume_errors_total` | Counter | `topic`, `error` | Monitors for Kafka consumption errors. Any value other than zero requires investigation. |
| `db_operation_latency_seconds` | Histogram | `repository`, `method` | Measures the latency of database operations. Spikes can indicate DB performance issues. |
| `outbox_events_published_total`| Counter | `aggregate_type`, `topic` | Tracks the number of `CashflowCalculated` events successfully published. |
| **`cashflows_created_total`** | **Counter** | **`classification`, `timing`**| **(New in RFC 022)** Provides a business-level count of generated cashflows. This is crucial for understanding the financial activity being processed (e.g., number of `INCOME` vs. `EXPENSE` flows). |

## 2. Common Failure Modes & Recovery

### Symptom: Consumer Lag is Increasing

- **Potential Cause 1: Database Performance**
  - **Check**: The `db_operation_latency_seconds` histogram in Grafana. Are `create_cashflow` operations becoming slow?
  - **Action**: Investigate the database for slow queries, high CPU usage, or connection pool exhaustion.

- **Potential Cause 2: Downstream Outage**
  - **Check**: The `outbox_events_pending` gauge. If this number is high and not decreasing, the outbox dispatcher is failing to publish events. This can be due to Kafka being unavailable.
  - **Action**: Check Kafka broker health and network connectivity from the service.

### Symptom: Messages are ending up in the DLQ

- **Potential Cause 1: Invalid Message Payload**
  - **Check**: The logs for the `cashflow_calculator_service`. Look for `ValidationError` or `JSONDecodeError` messages.
  - **Action**: The upstream service is likely publishing a malformed `TransactionEvent`. The message in the DLQ will need to be inspected to identify the schema violation.

- **Potential Cause 2: Missing Cashflow Rule**
  - **Check**: The processing outcome for reason code `cashflow_rule_missing`. This terminal error is emitted when a transaction is received for a type that does not have a corresponding entry in the `cashflow_rules` table.
  - **Action**: This is a configuration error. A business analyst or administrator needs to add a new rule to the `cashflow_rules` table for the missing transaction type. The affected message(s) can then be replayed from the DLQ.
