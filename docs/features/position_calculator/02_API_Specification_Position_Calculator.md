# Kafka Contract: Position Processing

The cost, cashflow, and position modules all run inside the unified `portfolio_transaction_processing_service`
deployment. It is a Kafka worker: it exposes no business REST API, only operational HTTP endpoints
for health, metrics, and build identity.

## 1. Health & Metrics API

* **Container port:** `8085`
* **Host default:** `http://localhost:8090` (override with `LOTUS_TRANSACTION_PROCESSING_HOST_PORT`)

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/health/live` | A liveness probe to confirm the service process is running. Returns `{"status": "alive"}`. |
| `GET` | `/health/ready` | A readiness probe that checks the service's ability to connect to the database. Returns `{"status": "ready"}` on success or a `503 Service Unavailable` on failure. |
| `GET` | `/metrics` | Exposes performance and application metrics in Prometheus format. |
| `GET` | `/version` | Returns the build identity of the running image. |

## 2. Kafka Interface

The service consumes from and produces to the same topic, forming a loop during reprocessing events.

### 2.1. Consumer

The service listens to a single topic:

#### Topic: `transactions.cost.processed`

* **Purpose:** This is the work queue. Each message represents a transaction whose cost effects have been applied and which is ready to be incorporated into the `position_history`.
* **Producer:** `portfolio_transaction_processing_service` — the cost module for new events, and the same runtime for replayed events.
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

### 2.2. Producer

#### Topic: `transactions.cost.processed`

* **Purpose:** Records each processed transaction as a `ProcessedTransactionPersisted` event.
  `TransactionalCostProcessingEffectStager.stage_processed_transactions`
  (`app/infrastructure/cost_basis/effect_staging.py`) stages one outbox row per transaction inside
  the same unit of work that persists the cost, cashflow, and position effects, so the event cannot
  be emitted for work that did not commit. It is staged for every processed transaction, not only
  during reprocessing.
* **Consumer:** none at runtime. The event-supportability contract records this family with
  `consumer_services=()` and `runtime_active=False`; it is staged as a compatibility event, not a
  work queue. The unified runtime subscribes to `transactions.persisted` and
  `transactions.reprocessing.requested` only, so do not trace replay or lag through a self-loop on
  this topic — position effects are applied inside the atomic transaction-processing use case before
  this event is staged.
* **Key:** `portfolio_id`
* **Payload (`TransactionEvent`):** The event business payload of the processed transaction,
  carrying its `epoch`. Reprocessing raises the epoch for the affected key, so events staged after a
  back-dated correction carry the higher value. Epoch fencing is enforced by the epoch-aware query
  and derived-state reads against durable state, not by consuming this topic — it has no runtime
  consumer.
    ```json
    {
        "transaction_id": "HISTORICAL_TXN_001",
        // ... all other fields
        "epoch": 1 // The epoch has been incremented
    }
    ```