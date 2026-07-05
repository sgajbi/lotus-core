# CR-1388 Worker Runtime Readiness

- Date: 2026-07-06
- Status: Hardened locally
- GitHub issue: #563
- Control taxonomy: operability, readiness, worker runtime supportability, testing

## Objective

Make worker readiness reflect the ability to process work, not only database reachability.

## Finding

Kafka-backed worker health apps commonly exposed `/health/ready` with only the `db` dependency.
Their consumer managers already detected critical task exits through `runtime_supervision`, but that
state was not visible through readiness responses. A process could therefore look ready while its
consumer, dispatcher, scheduler, or embedded runtime task had exited.

## Change

Added `portfolio_common.worker_readiness` with a shared `worker_runtime` dependency contract:

1. worker managers register their critical task set by health service name,
2. readiness reports bounded states such as `ok`, `failed`, `stopping`, or `misconfigured`,
3. runtime supervision marks failed and explicit shutdown states,
4. shared health routing exposes `worker_runtime` as a dependency alongside `db` and `kafka`.

Applied the contract to the existing web-backed Kafka worker services:

1. cost calculator,
2. position calculator,
3. cashflow calculator,
4. position valuation calculator,
5. pipeline orchestrator,
6. portfolio aggregation,
7. persistence,
8. timeseries generator,
9. valuation orchestrator.

## Compatibility

Liveness remains lightweight. Health response shape remains `status`, `dependencies`, and
`runtime`; readiness now includes additive bounded dependency keys for the worker services. No
business API route, database schema, Kafka topic, event payload, OpenAPI business contract, metric
name, or runtime deployment topology changed.

## Same-Pattern Scan

The slice scanned every existing web-backed worker health app using `create_standard_health_app`
and every matching consumer manager using `wait_for_shutdown_or_task_failure`. A static regression
test now requires each worker health app to declare `WORKER_READINESS_SERVICE_NAME`, include
`worker_runtime`, and pass that same service name into runtime supervision.

## Validation

Focused validation before commit:

1. `python -m pytest tests/unit/libs/portfolio-common/test_health.py tests/unit/libs/portfolio-common/test_runtime_supervision.py tests/unit/libs/portfolio-common/test_worker_readiness.py tests/unit/libs/portfolio-common/test_worker_readiness_wiring.py tests/unit/libs/portfolio-common/test_worker_runtime.py -q`
2. Scoped Ruff check/format on touched health, runtime, worker, and test files.
3. Representative service import proofs for worker health apps and consumer managers.
4. `make architecture-guard`
5. `make quality-wiki-docs-gate`

## Guidance Decision

Repository context was updated because this is a repo-local runtime/readiness contract for worker
services. No platform skill update was needed; existing backend delivery and review skills already
require same-pattern scans and durable guidance review. No wiki update was required because no
operator runbook, incident workflow, or public navigation changed in this slice.
