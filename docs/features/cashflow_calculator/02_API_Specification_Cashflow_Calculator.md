# API Specification: Cashflow Calculator

The `cashflow_calculator_service` is a headless service whose primary interface is Apache Kafka. It does not have a traditional REST API for its core logic but exposes standard HTTP endpoints for health and metrics monitoring.

## 1. Health & Metrics API

* **Base URL:** `http://localhost:8082`

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/health/live` | A liveness probe to confirm the service process is running. Returns `{"status": "alive"}`. |
| `GET` | `/health/ready` | A readiness probe that checks the service's ability to connect to the database. Returns `{"status": "ready"}` on success or a `503 Service Unavailable` on failure. |
| `GET` | `/metrics` | Exposes performance and application metrics in Prometheus format. |

## 2. Kafka Interface

The service's main function is to consume, process, and produce Kafka events.

### 2.1. Consumer

The service listens to a single topic:

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