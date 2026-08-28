# Kafka Contract: Cashflow Processing

The cost, cashflow, and position modules all run inside the unified `portfolio_transaction_processing_service`
deployment. It is a Kafka worker: it exposes no business REST API, only operational HTTP endpoints
for health, metrics, and build identity.

## 1. Health & Metrics API

* **Container port:** `8085`
* **Host default:** `http://localhost:8090` (override with `LOTUS_TRANSACTION_PROCESSING_HOST_PORT`)

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/health/live` | A liveness probe to confirm the service process is running. Returns `{"status": "alive"}`. |
| `GET` | `/health/ready` | A readiness probe over **three** dependencies — `db`, `kafka`, and `worker_runtime` (declared in `app/web.py`). Returns `{"status": "ready"}` on success or `503 Service Unavailable` on failure, with per-dependency detail in the body. A 503 is not necessarily a database problem: read the body to see which dependency failed. |
| `GET` | `/metrics` | Exposes performance and application metrics in Prometheus format. |
| `GET` | `/version` | Returns the build identity of the running image. |

## 2. Kafka Interface

The service's main function is to consume, process, and produce Kafka events.

### 2.1. Consumer

Cashflow has no Kafka topic of its own. It is one of three effects — cost, cashflow, and position —
applied inside a single atomic use case, so there is no separate cashflow work queue.

The unified deployment builds five consumers, listed in full in
[the transaction-processing Kafka contract](../cost_calculator/02_API_Specification_Cost_Calculator.md#21-consumers).
**All five can drive cashflow generation** — two directly, three by staging work that reaches the
same atomic use case on a later hop:

| Consumer group | Drives cashflow |
| --- | --- |
| `portfolio_transaction_processing_group` | Directly, for newly persisted transactions. |
| `portfolio_transaction_replay_request_group` | Directly, on replay of an affected key. |
| `corporate_action_manifest_group` | Indirectly — governed corporate actions. |
| `fixed_income_book_cost_authority_group` | **Not** for original creation; revises cashflows on already-booked transactions. |
| `fixed_income_book_cost_correction_replay_group` | **Not** for original creation; the second hop of that revision. |

For a governed corporate-action child, `TransactionProcessingConsumer` records the child *without
financial mutation*; the manifest makes its release eligible and
`ProcessNextCorporateActionReleaseUseCase` then invokes `ProcessTransactionUseCase`, which carries
the cashflow effect. The fixed-income path is two hops: the authority consumer stages
`fixed_income.book_cost.disposal_replay.requested`, and the correction-replay consumer republishes
the canonical transaction through the same atomic use case.

**A missing cashflow is never explained by the fixed-income groups.**
`_stage_correction_replay()` stages work only for a newly committed profile decision, and only when
`find_earliest_affected_disposal()` finds an already-persisted disposal — whose cashflow was
committed atomically during the original transaction processing. The correction consumer replays
that booked transaction to apply revised book-cost authority. A stall there leaves cost basis and
revised cashflow values stale; it cannot explain a cashflow that was never created.

For a **missing** cashflow, the relevant groups are `portfolio_transaction_processing_group`,
`portfolio_transaction_replay_request_group`, and — for governed corporate actions —
`corporate_action_manifest_group`, which can stall while the primary group stays current.

The subscription detailed below is the direct one:

#### Topic: `transactions.persisted`

* **Purpose:** This is the primary work queue for the service. Each message represents a raw transaction that has been persisted and is ready for cashflow generation.
* **Producer:** `persistence_service`
* **Key:** `portfolio_id`
* **Payload (`TransactionEvent`):**
    ```json
    {
      "transaction_id": "TXN_001",
      "portfolio_id": "PORT_001",
      "security_id": "SEC_AAPL",
      "transaction_date": "2025-08-15T10:00:00Z",
      "transaction_type": "BUY",
      "quantity": 10.0,
      "price": 150.0,
      "gross_transaction_amount": 1500.0,
      "trade_currency": "USD",
      "currency": "USD",
      "trade_fee": 5.0,
      "epoch": 0
    }
    ```

### 2.2. Producer (via Outbox)

The service produces events to one topic after successfully generating a cash flow record.

#### Topic: `cashflows.calculated`

* **Purpose:** This event signals that a cash flow record has been successfully created for a transaction. This event is not currently consumed by any downstream services but is available for future use (e.g., auditing, real-time dashboards).
* **Consumer:** (None currently)
* **Key:** `portfolio_id`
* **Payload (`CashflowCalculatedEvent`):**
    ```json
    {
      "cashflow_id": 12345,
      "transaction_id": "TXN_001",
      "portfolio_id": "PORT_001",
      "security_id": "SEC_AAPL",
      "cashflow_date": "2025-08-15",
      "amount": -1505.50,
      "currency": "USD",
      "classification": "INVESTMENT_OUTFLOW",
      "timing": "BOD",
      "calculationType": "NET",
      "is_position_flow": true,
      "is_portfolio_flow": false,
      "epoch": 0
    }
    ```