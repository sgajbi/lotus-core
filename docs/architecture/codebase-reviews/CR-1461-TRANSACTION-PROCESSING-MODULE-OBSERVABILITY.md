# CR-1461: Transaction Processing Module Observability

Date: 2026-07-10
Issue: #468
Status: Hardened locally; runtime cutover pending

## Objective

Preserve cost, cashflow, position, commit, and replay attribution after three calculator workers
become one transaction-processing deployable, without coupling application logic to Prometheus.

## Implementation

- Added a framework-neutral observer port with governed operation and outcome enums.
- Injected the observer into live and replay application use cases.
- Added a Prometheus infrastructure adapter for operation counts and durations.
- Recorded overall `processed`, `duplicate`, `rejected`, `failed`, `replayed`, and `not_found`
  outcomes plus idempotency, cost, cashflow, position-leg, and commit success/failure timing.
- Registered both service-local metrics to `portfolio_transaction_processing_service`.

The exported metrics are:

- `lotus_core_transaction_processing_operations_total{stage,outcome}`;
- `lotus_core_transaction_processing_operation_duration_seconds{stage,outcome}`.

Both labels are bounded enums. Portfolio, transaction, event, correlation, trace, exception, and
error text are excluded. Metric-recording failures are logged and cannot change financial-state
processing or rollback behavior.

## Validation Evidence

- target unit pack: 65 passed;
- PostgreSQL atomic unit-of-work pack: 4 passed in 64.49 seconds;
- target MyPy: passed for 34 source files;
- metric vocabulary, application-port, dependency-inversion, infrastructure-adapter,
  in-process-boundary, strict-architecture, and observability-contract-pack guards: passed;
- scoped Ruff lint/format and diff checks: passed.

## Compatibility And Remaining Work

No API, Kafka topic/group/payload, database schema, outbox contract, retry policy, transaction
result, or commit boundary changed. The observer is composed only inside the undeployed target.

This closes module outcome/error/latency attribution only. Consumer lag, DB/Kafka/outbox
diagnostics, tracing export, dashboard panels, alert thresholds, and the target support runbook
remain required before runtime cutover.

No README or wiki change is required while the target remains undeployed. Update both when the
combined runtime becomes current operator truth.
