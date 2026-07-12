# CR-1429: Transaction Worker Runtime Composition

Date: 2026-07-10  
Issue: #468  
Status: Hardened locally

## Objective

Remove repeated worker runtime orchestration from cost, cashflow, and position services before
building their combined transaction-processing host.

## Finding

All three consumer managers independently verified topics, registered process signals, configured
the health server, created consumer/dispatcher/server tasks, supervised failure, and shut runtime
components down. This repeated lifecycle code increased design complexity and made a combined host
more difficult to introduce safely.

## Change

- Added `run_kafka_worker_runtime(...)` to shared worker runtime composition.
- Migrated cost, cashflow, and position consumer managers to the shared runtime helper.
- Preserved service-local consumer construction, topics, groups, ports, readiness service names,
  signal logging, and web applications.
- Added direct shared-runtime composition coverage and retained each service's graceful-shutdown
  and fail-fast tests.

The three manager modules reduced from 321 to 251 lines. Runtime lifecycle policy now has one owner.

## Compatibility

No calculation, Kafka topic, consumer group, event payload, idempotency key, retry profile, DLQ,
database transaction, outbox payload, health port, metric, image, Compose service, route, or OpenAPI
contract changed. This is design modularity inside the current three deployables.

## Evidence

- Shared worker runtime plus three calculator manager suites -> 13 passed.
- Scoped Ruff lint and format checks -> passed.
- `git diff --check` -> passed.

## Same-Pattern Decision

Position valuation is intentionally not migrated in this slice because it remains outside the
transaction-processing consolidation target. The shared helper is reusable if later evidence shows
that valuation should adopt the same lifecycle composition without changing its runtime boundary.

No README, wiki, central skill, or platform context change is required. The consolidation decision
and repository context already describe this prerequisite and the target structure.
