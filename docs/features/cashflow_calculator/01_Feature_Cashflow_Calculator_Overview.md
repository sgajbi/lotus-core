# Feature: Cashflow Calculator

The **Cashflow Calculator** service is a core component of the system responsible for translating raw financial transactions into standardized cashflow records. These records are essential for all higher-level performance and time-series calculations.

## 1. Core Responsibilities

- **Consumption**: Listens to the `transactions.cost.processed` Kafka topic for new, validated transaction events.
- **Enrichment**: For each transaction, it applies a set of business rules to determine the cashflow's financial characteristics.
- **Calculation**: It calculates the net cashflow amount, adjusting for fees and applying the correct sign (inflow/outflow).
- **Persistence**: Saves the resulting `Cashflow` record to the main database.
- **Publication**: Publishes a `CashflowCalculated` event to the `cashflows.calculated` topic via the outbox pattern for downstream consumers like the `timeseries_generator_service`.

## 2. Key Features

### Database-Driven Business Logic

The rules that map a transaction type (e.g., "BUY", "DIVIDEND") to a cashflow's financial properties are not hardcoded. Instead, they are stored in the `cashflow_rules` database table.

This provides significant business agility, as a financial analyst can modify how transactions are treated without requiring a developer to change code or redeploy the service. The service loads these rules into an in-memory cache at startup for high performance.

### Idempotency and Reliability

The consumer is fully idempotent. It tracks processed event IDs in the `processed_events` table to ensure that a duplicated message from Kafka will not result in a duplicate cashflow record. All database writes and event publications are wrapped in a single atomic transaction using the outbox pattern.

### Observability

The service is instrumented with Prometheus metrics to provide deep insight into its operational health and business activity. See the [Operations & Troubleshooting Guide](./04_Operations_Troubleshooting_Guide.md) for a full list of available metrics.
