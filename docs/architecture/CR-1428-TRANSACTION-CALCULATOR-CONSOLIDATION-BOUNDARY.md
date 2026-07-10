# CR-1428: Transaction Calculator Consolidation Boundary

Date: 2026-07-10  
Issue: #468  
Status: In progress

## Objective

Turn calculator consolidation into a governed target with explicit stage ownership, dependency
rules, compatibility constraints, and rollback gates.

## Finding

Cost, cashflow, and position workers form one ordered transaction-processing capability but repeat
321 lines of consumer-manager runtime wiring, 261 Dockerfile lines, overlapping dependency
packaging, three health servers, and three outbox dispatcher loops. Their domain rules remain
independently testable, while normal booked-transaction effects should become one atomic unit of
work to eliminate partial pipeline completion.

Valuation is not part of this consolidation because it is job-driven, market-data dependent,
compute-heavy, independently scalable, and operationally distinct from transaction processing.

## Change

- Planned one `portfolio_transaction_processing_service` and `ProcessTransactionUseCase` target
  for cost, cashflow, and position.
- Added a decision record with preserved contracts, phased migration, parity gates, and rollback.
- Added `runtime-consolidation-planned` catalog governance with a required target service id.
- Documented input, output, idempotency, replay, state, and read-model ownership per pipeline stage.
- Blocked calculator imports of orchestrator/query internals and orchestrator imports of
  calculator/query internals.
- Updated repository context, README, architecture index, and wiki source with current-versus-target
  truth.

## Compatibility

This slice changes design and governance truth only. Current Dockerfiles, Compose services, Kafka
topics, consumer groups, event payloads, idempotency keys, database schemas, metrics, health ports,
routes, and OpenAPI contracts remain unchanged.

## Evidence

- Runtime-boundary and architecture guard unit tests -> 25 passed.
- Direct runtime-boundary decision guard -> passed.
- Strict architecture boundary guard -> passed.
- Scoped Ruff lint and format checks -> passed.
- Documentation catalog and wiki checks are required before commit.
- `git diff --check` -> passed.

## Remaining Work

Issue #468 stays open until the shared runtime/package prerequisite, combined host, failure/replay
proof, deployment switch, image proof, canonical QA, and removal of the three old deployables are
complete. This entry does not overstate planned consolidation as runtime completion.
