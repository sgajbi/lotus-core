# Effective-Dated FX Revaluation

## Objective

Close the correctness gap where an accepted FX-rate correction became durable but existing
position snapshots and position/portfolio time series retained the superseded rate until unrelated
work or manual replay occurred.

## Findings

Persistence had no source-owned persisted FX observation event, valuation orchestration had no FX
consumer, and durable reprocessing was keyed only by security-price corrections. The same missing
ownership affected current and backdated rates, readiness races, duplicate delivery, support
diagnostics, corrected P&L evidence, and repeatable workload certification.

Concurrent pair corrections exposed a second defect: the partial unique index prevented duplicate
pending jobs, but conflict arrival order could select source lineage. Earliest economic impact and
newest source evidence are independent facts and must be coalesced independently.

Initial reference-data loads exposed a third defect: a pair with no affected position returned to
`PENDING` immediately and bypassed stale-processing max-attempt handling, allowing an unbounded
claim/no-op loop.

The repository-wide leakage guard exposed a fourth defect: bank-day JSON and Markdown evidence
persisted the credentialed host database URL. Ignored local output is still evidence that may be
retained or shared, so credentials cannot be part of its schema.

The first certifying five-day run exposed a fifth defect: the scheduler could claim and publish
`batch_size * dispatch_rounds` jobs every two seconds without considering already dispatched work.
One sequential Kafka partition therefore left about 60,000 database rows in `PROCESSING`; queued
messages aged past the worker stale timeout and were eventually marked `FAILED` despite never
having started valuation execution.

## Implemented Direction

1. Persistence emits a versioned, deterministic, source-owned FX persisted event through the
   transactional outbox.
2. Delivery maps Kafka payloads to application commands; application coordination and direct-pair
   policy remain framework independent.
3. Valuation orchestration stages immediate affected-position work and one durable pending replay
   per direct pair without a global portfolio scan.
4. Durable replay preserves the earliest impacted date and deterministic newest source lineage,
   including under independent concurrent database sessions.
5. No-exposure work retries only for the configured visibility-race limit, then completes as an
   observable no-op; a future valuation reads the already-corrected durable FX rate.
6. Shared workers execute pair replay, regenerate snapshots and derived time series, and expose
   queue/outcome metrics plus portfolio-scoped Query Control Plane diagnostics.
7. The managed FX-restatement profile uses an independent oracle for corrected market value and
   unrealized price, FX, and total P&L, then requires exactly-once source/replay evidence and closed
   queues. It commits the correction while valuation orchestration is stopped and proves recovery
   after unconditional service restoration. Measured stop/restore timestamps and outage duration
   replace caller-asserted recovery flags.
8. Workload reports retain only a safe database target and exclude URL credentials and parameters;
   generated evidence must pass the leakage guard.
9. Valuation claims enforce one configurable durable in-flight ceiling across scheduler replicas.
   A PostgreSQL transaction-scoped advisory lock makes the capacity check and claim mutually
   exclusive, preventing queue backlog from growing beyond worker drain capacity.

## Compatibility

External API routes and existing event consumers are unchanged. The persisted FX event is an
additive internal versioned contract. Query Control Plane adds truthful support records for the new
job family. Database changes are additive indexes supporting bounded pair work. Inverse and
triangulated conversion are intentionally unsupported by this trigger and are never inferred.

## Validation Status

Unit, contract, strict typing, architecture, OpenAPI, migration, PostgreSQL lifecycle, and QCP
support tests pass in focused slices. Managed Kafka/runtime, restart, concurrent-session, and
five-business-date exact-value evidence are required before #791 can move to `status/fixed-local`.

## Documentation Decision

Operations docs, authored wiki, repository context, event/support inventories, and this review
record change because runtime ownership and support procedures changed. No public OpenAPI business
route changed; the existing QCP support-family OpenAPI was extended and tested in the implementation
slice.
