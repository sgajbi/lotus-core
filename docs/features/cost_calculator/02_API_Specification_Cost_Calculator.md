# Kafka Contract: Transaction Processing

The `portfolio_transaction_processing_service` is the unified transaction-economics runtime for
cost, cashflow, and position processing. Its primary interface is Apache Kafka. It also exposes
standard HTTP endpoints for health and metrics monitoring.

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
* **Producer:** `ingestion_service` or `event_replay_service`.
* **Key:** source-owned `portfolio_id`
* **Payload:**
    ```json
    {
      "transaction_id": "TXN_001",
      "portfolio_id": "PORT_001"
    }
    ```

The public API remains transaction-id based. Before publishing, Core resolves each transaction
against the canonical ledger and adds its portfolio identity. Consumers continue to accept the
legacy transaction-id-only payload during the compatibility window, but enriched commands must
carry a `portfolio_id` that matches the Kafka key.

### 2.2. Producers (via Outbox)

The service produces events to two different topics depending on the flow:

#### Topic: `transactions.cost.processed`

* **Purpose:** This event signals that a transaction has been successfully processed and enriched with cost basis and/or realized P&L information.
* **Consumer:** No active runtime consumer; retained as a compatibility fact.
* **Key:** `portfolio_id`
* **Payload (`TransactionEvent`):** The payload is the full, enriched `TransactionEvent`, now including calculated fields like `net_cost`, `realized_gain_loss`, `transaction_fx_rate`, etc.

#### Topic: `transactions.persisted` (Reprocessing Flow)

* **Purpose:** When triggered by the `transactions.reprocessing.requested` topic, the consumer re-publishes the original raw transaction event back to this topic to restart the calculation pipeline for that specific transaction.
* **Consumer:** The unified `portfolio_transaction_processing_service`.
* **Key:** `portfolio_id`
* **Payload (`TransactionEvent`):** The original, raw `TransactionEvent` as it exists in the database.
