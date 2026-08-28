# Feature: Cashflow Processing

**Cashflow processing** translates raw financial transactions into standardized cashflow records. It is not a separate deployment: it is one of three effects — cost, cashflow, and position — applied inside a single atomic use case in the unified `portfolio_transaction_processing_service` runtime. These records are essential for all higher-level performance and time-series calculations.

## 1. Core Responsibilities

- **Consumption**: Driven by `TransactionProcessingConsumer` on `transactions.persisted`, with `transactions.reprocessing.requested` for replay. Cashflow has no subscription of its own, and nothing consumes `transactions.cost.processed` — that topic is an outbound compatibility fact.
- **Enrichment**: For each transaction, it applies a set of business rules to determine the cashflow's financial characteristics.
- **Calculation**: It calculates the net cashflow amount, adjusting for fees and applying the correct sign (inflow/outflow).
- **Persistence**: Saves the resulting `Cashflow` record to the main database.
- **Publication**: Publishes a retained `CashflowCalculated` compatibility fact to the
  `cashflows.calculated` topic through the outbox. No active Core stage waits on that topic;
  `portfolio_derived_state_service` reads the durable cashflow rows when valuation snapshots
  trigger position-timeseries materialization.

## 2. Key Features

### Database-Driven Business Logic

The rules that map a transaction type (e.g., "BUY", "DIVIDEND") to a cashflow's financial properties are not hardcoded. Instead, they are stored in the `cashflow_rules` database table.

This provides significant business agility: a financial analyst can modify how transactions are
treated without a developer changing code, **and without a redeploy or restart**.

`CashflowRuleCache.resolve()` (`app/infrastructure/cashflow/rule_cache.py`) holds a version-checked
snapshot rather than a load-once-at-startup cache. It populates lazily on first use and refreshes
the snapshot when any of three conditions hold: the TTL has expired
(`CASHFLOW_RULE_CACHE_TTL_SECONDS`, default 300 seconds), the source rule-set version no longer
matches the cached one, or the requested rule is absent — which forces an immediate reload.

So a rule change is picked up on its own. Restarting the deployment to apply one is unnecessary.

### Idempotency and Reliability

The consumer is fully idempotent. It tracks processed event IDs in the `processed_events` table to ensure that a duplicated message from Kafka will not result in a duplicate cashflow record. All database writes and event publications are wrapped in a single atomic transaction using the outbox pattern.

### Observability

The service is instrumented with Prometheus metrics to provide deep insight into its operational health and business activity. See the [Operations & Troubleshooting Guide](./04_Operations_Troubleshooting_Guide.md) for a full list of available metrics.
