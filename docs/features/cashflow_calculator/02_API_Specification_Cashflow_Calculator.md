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
The one that drives cashflow generation is:

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