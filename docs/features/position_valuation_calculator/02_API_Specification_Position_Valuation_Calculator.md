# API Specification: Position Valuation Calculator

The `position-valuation-calculator` is a headless service that does not have a traditional REST API for its core logic. Its primary interface is Apache Kafka. It does, however, expose standard HTTP endpoints for health and metrics monitoring.

## 1. Health & Metrics API

* **Base URL:** `http://localhost:8084`

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/health/live` | A liveness probe to confirm the service process is running. Returns `{"status": "alive"}`. |
| `GET` | `/health/ready` | A readiness probe that checks the service's ability to connect to the database. Returns `{"status": "ready"}` on success or a `503 Service Unavailable` on failure. |
| `GET` | `/metrics` | Exposes a wide range of performance and application metrics in Prometheus format. |

## 2. Kafka Interface

The service's main function is to consume, process, and produce Kafka events.

### 2.1. Consumers

The service listens to two topics:

#### Topic: `valuation.job.requested`

* **Purpose:** This is the primary work queue for the service. Each message represents a job to value a single position on a single day for a specific epoch.
* **Producer:** `ValuationScheduler` (within this same service).
* **Key:** `portfolio_id`
* **Payload (`PortfolioValuationRequiredEvent`):**
    ```json
    {
      "portfolio_id": "PORT_001",
      "security_id": "SEC_AAPL",
      "valuation_date": "2025-08-20",
      "epoch": 1,
      "correlation_id": "SCHEDULER_BACKFILL_2025-08-20"
    }
    ```

#### Topic: `market_prices.persisted`

* **Purpose:** This topic signals that a new market price has been saved to the database. The service consumes these events to detect if the price is for a past date, which would trigger a reprocessing flow.
* **Producer:** `persistence_service`
* **Key:** `security_id`
* **Payload (`MarketPricePersistedEvent`):**
    ```json
    {
      "security_id": "SEC_AAPL",
      "price_date": "2025-08-19",
      "price": 175.50,
      "currency": "USD"
    }
    ```

### 2.2. Producer (via Outbox)

The service produces events to one topic after successfully completing a valuation.

#### Topic: `valuation.snapshot.persisted`

* **Purpose:** This event signals that a `daily_position_snapshot` has been successfully created or updated with valuation data. This event is a critical trigger for the downstream `timeseries-generator-service`.
* **Consumer:** `timeseries-generator-service`
* **Key:** `portfolio_id`
* **Payload (`DailyPositionSnapshotPersistedEvent`):**
    ```json
    {
      "id": 54321,
      "portfolio_id": "PORT_001",
      "security_id": "SEC_AAPL",
      "date": "2025-08-20",
      "epoch": 1
    }
    ```