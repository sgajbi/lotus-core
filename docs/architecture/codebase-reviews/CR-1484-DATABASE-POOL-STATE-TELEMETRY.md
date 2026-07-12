# CR-1484: Database Pool State Telemetry

Date: 2026-07-10
Issue: #468
Status: Hardened locally; alert and deployed evidence pending

## Objective

Expose database connection-pool pressure for the combined transaction-processing worker through the
shared readiness path without coupling application or domain code to SQLAlchemy or Prometheus.

## Change

Successful database readiness checks now sample the active async SQLAlchemy pool and set:

`database_pool_connections{pool="async",state}`

The bounded `state` values are:

- `configured_capacity`;
- `checked_in`;
- `checked_out`;
- `overflow`.

SQLAlchemy may report negative overflow while the base pool is not yet full; the exported gauge
normalizes all counts to zero or greater. The `pool` label is registered in the shared metric
vocabulary. The scrape target remains the service identity, so no high-cardinality database URL,
session, transaction, portfolio, or request label is introduced.

## Failure And Performance Behavior

- Sampling uses in-process pool counters after the readiness transaction closes.
- No database query is added beyond the existing `SELECT 1` readiness probe.
- Sampling failure is isolated and cannot turn a healthy database readiness result into failure.
- A failed database check retains its existing unavailable result and dependency telemetry.

## Compatibility

The change is additive. Database connection settings, pool sizing, transaction/session ownership,
readiness status vocabulary, API schemas, and deployed topology are unchanged.

## Validation

- shared monitoring, health, and target health contract pack: `25 passed`;
- exact pool-state and negative-overflow normalization proof;
- telemetry failure non-interference proof;
- metric vocabulary, observability contract, MyPy, and full Ruff lint gates passed.

Dashboard ratios, alert thresholds, and deployed saturation evidence remain cutover prerequisites.
