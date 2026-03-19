# API Specification: Cost Calculator

The `cost_calculator_service` is a headless service that does not have a traditional REST API for its core logic. Its primary interface is Apache Kafka. It also exposes standard HTTP endpoints for health and metrics monitoring.

## 1. Health & Metrics API

* **Base URL:** `http://localhost:8083`

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/health/live` | A liveness probe to confirm the service process is running. Returns `{"status": "alive"}`. |
| `GET` | `/health/ready` | A readiness probe that checks the service's ability to connect to the database. Returns `{"status": "ready"}` on success or a `503 Service Unavailable` on failure. |
| `GET` | `/metrics` | Exposes performance and application metrics in Prometheus format. |

## 2. Kafka Interface

The service's function is to consume, process, and produce Kafka events.

### 2.1. Consumers

The service listens to two topics:

#### Topic: `transactions.persisted`

* **Purpose:** This is the primary work queue. Each message represents a raw transaction that has been successfully persisted and is ready for cost calculation.
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

#### Topic: `transactions.reprocessing.requested`

* **Purpose:** Consumes requests to reprocess a transaction.
* **Producer:** `ingestion_service` (via API) or `tools/reprocess_transactions.py` (via script).
* **Key:** `transaction_id`
* **Payload:**
    ```json
    {
      "transaction_id": "TXN_001"
    }
    ```

### 2.2. Producers (via Outbox)

The service produces events to two different topics depending on the flow:

#### Topic: `transactions.cost.processed`

* **Purpose:** This event signals that a transaction has been successfully processed and enriched with cost basis and/or realized P&L information.
* **Consumer:** `position-calculator-service`
* **Key:** `portfolio_id`
* **Payload (`TransactionEvent`):** The payload is the full, enriched `TransactionEvent`, now including calculated fields like `net_cost`, `realized_gain_loss`, `transaction_fx_rate`, etc.

#### Topic: `transactions.persisted` (Reprocessing Flow)

* **Purpose:** When triggered by the `transactions.reprocessing.requested` topic, the consumer re-publishes the original raw transaction event back to this topic to restart the calculation pipeline for that specific transaction.
* **Consumer:** Itself (`cost-calculator-service`).
* **Key:** `portfolio_id`
* **Payload (`TransactionEvent`):** The original, raw `TransactionEvent` as it exists in the database.