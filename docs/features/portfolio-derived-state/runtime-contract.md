# Portfolio Derived-State Runtime Contract

The `portfolio_derived_state_service` is a headless worker whose inbound event interface is Apache
Kafka. It does not have a traditional REST API for its core logic but exposes standard HTTP
endpoints for health and metrics monitoring. Its downstream handoff is the durable
`portfolio_aggregation_jobs` database queue, not a second Kafka topic.

## 1. Health & Metrics API

* **Base URL:** `http://localhost:8085`

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/health/live` | A liveness probe to confirm the service process is running. Returns `{"status": "alive"}`. |
| `GET` | `/health/ready` | A readiness probe that checks the service's ability to connect to the database. Returns `{"status": "ready"}` on success or a `503 Service Unavailable` on failure. |
| `GET` | `/metrics` | Exposes performance and application metrics in Prometheus format. |
| `GET` | `/version` | Exposes commit, branch, build timestamp, repository, image version/digest, CI run ID, and matching OCI-label metadata. |

## 2. Kafka Interface

The service consumes persisted valuation snapshots and generates position-level time-series data.

### 2.1. Consumers

The service listens to one topic:

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

### 2.2. Durable Aggregation Handoff

After position materialization, the service idempotently stages one
`portfolio_aggregation_jobs` row for every affected portfolio date. Its scheduler leases complete
jobs directly from PostgreSQL and bounded workers invoke the portfolio-timeseries use case. The
queue is the durable internal command boundary; there is no private aggregation Kafka topic.

The preserved consumer group is `timeseries_generator_group_positions`. Keeping this identifier is
an intentional offset-compatibility decision, not a surviving legacy service.
