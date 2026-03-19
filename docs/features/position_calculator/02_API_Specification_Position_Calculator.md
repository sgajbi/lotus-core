# API Specification: Position Calculator

The `position_calculator_service` is a headless service whose primary interface is Apache Kafka. It does not have a traditional REST API for its core logic but exposes standard HTTP endpoints for health and metrics monitoring.

## 1. Health & Metrics API

* **Base URL:** `http://localhost:8081`

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/health/live` | A liveness probe to confirm the service process is running. Returns `{"status": "alive"}`. |
| `GET` | `/health/ready` | A readiness probe that checks the service's ability to connect to the database. Returns `{"status": "ready"}` on success or a `503 Service Unavailable` on failure. |
| `GET` | `/metrics` | Exposes performance and application metrics in Prometheus format. |

## 2. Kafka Interface

The service consumes from and produces to the same topic, forming a loop during reprocessing events.

### 2.1. Consumer

The service listens to a single topic:

#### Topic: `transactions.cost.processed`

* **Purpose:** This is the work queue. Each message represents a transaction that has been enriched by the `cost_calculator_service` and is ready to be incorporated into the `position_history`.
* **Producer:** `cost_calculator_service` (for new events), or Itself (for replayed events).
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
      "net_cost": 1505.0,
      "trade_currency": "USD",
      "currency": "USD",
      "trade_fee": 5.0,
      "epoch": 0
    }
    ```

### 2.2. Producer (Reprocessing Flow)

The service only produces messages when it triggers a reprocessing flow.

#### Topic: `transactions.cost.processed`

* **Purpose:** When a back-dated transaction is detected, this service re-publishes all historical transactions for that security to this same topic. This ensures the entire history is re-calculated deterministically.
* **Consumer:** Itself (`position_calculator_service`) and other services like `cashflow_calculator_service`.
* **Key:** `portfolio_id`
* **Payload (`TransactionEvent`):** The payload is the same as the consumed event, with one critical difference: the `epoch` field is incremented to the new, higher version number. This is the signal for all consumers to perform epoch fencing.
    ```json
    {
        "transaction_id": "HISTORICAL_TXN_001",
        // ... all other fields
        "epoch": 1 // The epoch has been incremented
    }
    ```