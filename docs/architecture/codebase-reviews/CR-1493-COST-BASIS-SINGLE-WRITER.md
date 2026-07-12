# CR-1493: Cost-Basis Single Writer

Date: 2026-07-11
Issues: #484, #468
Status: Implemented locally; deployed contention baseline pending

## Objective

Prevent an older FIFO, AVCO, backdated, or replay calculation from overwriting newer lot and
cost-basis state while retaining parallel processing across unrelated securities.

## Finding

The ordered cost checkpoint and AVCO aggregate row lock improved incremental throughput, but they
did not provide one coordination boundary for every state transition. FIFO selected-lot updates,
full rebuilds, first-write upserts, and historical AVCO reconciliation could read state before a
concurrent calculation committed and later persist a stale replacement.

Kafka key ordering is useful delivery control, but it is not a database correctness fence across
live, replay, repair, or independently scheduled callers.

## Implementation

- Added a stable signed 64-bit advisory transaction-lock key derived from normalized portfolio and
  security identifiers.
- Acquired the lock before the shared cost workflow reads its processing checkpoint, open lots, or
  transaction history.
- Applied the same lock to historical AVCO reconciliation before canonical replay and comparison.
- Retained the AVCO aggregate row lock as a local persistence invariant; the key lock additionally
  covers absent aggregate rows, FIFO, rebuild, and repair paths.
- Added `cost_basis_processing_lock_wait_seconds` with bounded `acquired` and `failed` outcomes,
  structured support logs, and an app-local dashboard panel.
- Propagated lock failures so the caller-owned unit of work rolls back and the governed delivery
  retry/DLQ policy remains authoritative.

## Audit Identity

`PositionLotState` retains the source acquisition's calculation policy id/version.
`CostBasisProcessingState` records the committed portfolio/security frontier with cost-basis
method, latest calculation transaction id, and engine state version. PostgreSQL proof asserts both
records after concurrent processing, so operators can identify the source policy and the exact
calculation frontier that produced current lot state without adding a duplicate run table.

## Correctness And Scalability Evidence

A PostgreSQL overlap test pauses BUY processing after it has read canonical history while holding
the real advisory lock. A SELL and a replay reach the same lock and remain blocked. After the BUY
commits, both waiting calculations recompute from committed state and converge to one FIFO lot with
`40` open units and `400` local/base basis. The checkpoint identifies the SELL and `open-lot-v1`;
the lot retains the governed BUY policy and version.

A separate two-session test holds one key and proves another security in the same portfolio can
acquire immediately. Coordination therefore serializes only the mutable cost-basis aggregate, not
the portfolio, worker, or database.

The same-pattern scan found two production mutation boundaries: the shared cost workflow and the
historical AVCO reconciliation adapter. Both are fenced. Direct lot mutation methods are otherwise
used only behind those boundaries or in repository tests.

## Architecture And Compatibility

This is design hardening inside the unified transaction-processing deployable. It does not add a
service, consumer, lock table, event, API, migration, or downstream contract. Cost, cashflow, and
position remain separate domain/application modules coordinated by one atomic use case. The lock
adds one constant-time PostgreSQL statement per cost-basis calculation and preserves cross-key
parallelism.

## Validation

- Repository, workflow, and reconciliation cohort: `30 passed`.
- PostgreSQL concurrency module: `2 passed in 35.45s`.
- Repository-native transaction-processing contract: `31 passed in 127.07s`.
- Dashboard contract: `4 passed`.
- Ruff and MyPy passed for all touched Python modules.
- Wiki/docs, strict architecture, domain-layer, dependency-inversion, repository-transaction,
  modularity, and in-process boundary gates passed.

## Remaining Deployment Evidence

Capture lock-wait p50/p95/p99, failed acquisitions, database-pool wait/utilization, transaction
latency, partition lag, retry/DLQ behavior, and recovery under controlled live plus replay load.
Set alerts only after reviewing that baseline. No platform skill change is required: current
backend-delivery, issue-resolution, and codebase-review skills already require a same-pattern scan,
database concurrency proof, bounded telemetry, and durable repository guidance.
