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

The same run exposed a sixth bottleneck: app-local Kafka created one partition and the valuation
runtime constructed one serial consumer. Correctly bounded dispatch would therefore avoid false
failures but still take several hours to drain the five-day workload.

The first full drain exposed a seventh correctness defect: valuation backfill and watermark
contiguity iterated calendar days even though the workload seeded five governed business dates.
That created weekend snapshots and made the source-row oracle correctly reject the inflated scope.

The corrected-rate phase exposed an eighth correctness defect: position time series stores
instrument-local values, which can remain numerically unchanged when only portfolio-base FX
changes. Material-change suppression therefore skipped the freshness write and never rearmed
portfolio aggregation for the newer authoritative snapshot.

## Implemented Direction

1. Persistence emits a versioned, deterministic, source-owned FX persisted event through the
   transactional outbox.
2. Delivery maps Kafka payloads to application commands; application coordination and direct-pair
   policy remain framework independent.
3. Valuation orchestration stages immediate affected-position work. Backdated and future
   observations also stage one durable pending replay per direct pair without a global portfolio
   scan. Current-date observations do not create replay for positions that do not yet exist because
   later transaction readiness consumes the already committed rate.
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
10. Position valuation supports an explicit in-process worker count. App-local Compose creates
    eight topic partitions and runs eight serial consumers, preserving per-portfolio broker order
    while allowing different portfolios to value concurrently.
11. Backfill planning resolves the seeded `GLOBAL` business dates once per scheduler batch and
    filters them per position. Watermark contiguity uses the same governed dates, including the
    previous governed date before a gap. Calendar-day fallback remains only for recovery when the
    governed calendar is entirely empty.
12. Position materialization compares authoritative snapshot freshness with the existing
    time-series materialization timestamp. A newer snapshot refreshes the row and rearms portfolio
    aggregation even when local-currency values are unchanged; duplicate delivery after freshness
    catches up remains a no-op.
13. Price and FX observations share one temporal scheduling policy. Current-date facts use
    immediate visible-position jobs and later transaction readiness; backdated and future facts
    retain durable replay. This prevents reference-data startup from resetting newly created
    position epochs and amplifying valuation work.

## Compatibility

External API routes and existing event consumers are unchanged. The persisted FX event is an
additive internal versioned contract. Query Control Plane adds truthful support records for the new
job family. Database changes are additive indexes supporting bounded pair work; the business-date
and source-freshness fixes require no schema change. Inverse and triangulated conversion are
intentionally unsupported by this trigger and are never inferred.

## Validation Status

Unit, contract, strict typing, architecture, OpenAPI, migration, PostgreSQL lifecycle, and QCP
support tests pass. Managed certifying run `20260715T233241Z` completed successfully over exactly
five governed business dates: 12,500/12,500 affected snapshots, valuation jobs, and position rows;
500/500 portfolio rows; one persisted observation; one completed pair replay; exact corrected
market value and unrealized price/FX/total P&L; a measured `6.167s` orchestrator outage with healthy
restore; 292 complete resource samples; zero failures; and closed valuation, aggregation, and
outbox queues. This is local closure evidence for #791 pending PR, CI, exact-main validation, QA,
and issue closure.

## Documentation Decision

Operations docs, authored wiki, repository context, event/support inventories, and this review
record change because runtime ownership and support procedures changed. No public OpenAPI business
route changed; the existing QCP support-family OpenAPI was extended and tested in the implementation
slice.
