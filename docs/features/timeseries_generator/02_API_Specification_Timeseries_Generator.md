# API Specification: Timeseries Generator

The `timeseries_generator_service` is a headless service whose primary interface is Apache Kafka. It does not have a traditional REST API for its core logic but exposes standard HTTP endpoints for health and metrics monitoring.

## 1. Health & Metrics API

* **Base URL:** `http://localhost:8085`

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/health/live` | A liveness probe to confirm the service process is running. Returns `{"status": "alive"}`. |
| `GET` | `/health/ready` | A readiness probe that checks the service's ability to connect to the database. Returns `{"status": "ready"}` on success or a `503 Service Unavailable` on failure. |
| `GET` | `/metrics` | Exposes performance and application metrics in Prometheus format. |

## 2. Kafka Interface

The service consumes events, generates time-series data, and produces new events to orchestrate its own workflow.

### 2.1. Consumers

The service listens to two topics:

#### Topic: `valuation.snapshot.persisted`

* **Purpose:** This is the primary trigger for position-level time-series generation. Each message signals that a new or updated daily position snapshot is ready.
* **Producer:** `position-valuation-calculator`
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

#### Topic: `portfolio_day.aggregation.job.requested`

* **Purpose:** This is the work queue for the portfolio-level aggregation. Each message is a job to aggregate all of a portfolio's position time-series records for a single day.
* **Producer:** `AggregationScheduler` (within `portfolio_aggregation_service`).
* **Key:** `portfolio_id`
* **Payload (`PortfolioAggregationRequiredEvent`):**
    ```json
    {
      "portfolio_id": "PORT_001",
      "aggregation_date": "2025-08-20",
      "correlation_id": "SCHEDULER_JOB_XYZ"
    }
    ```

### 2.2. Producers

The service's components produce events to orchestrate the aggregation workflow.

#### Topic: `portfolio_day.aggregation.job.requested`

* **Purpose:** The `AggregationScheduler` component of `portfolio_aggregation_service` produces messages to this topic. `timeseries_generator_service` consumes those work assignments but does not own the scheduler.
* **Key:** `portfolio_id`
* **Payload (`PortfolioAggregationRequiredEvent`):** (Same as the consumed event).
