# CR-1492: Position Recalculation Single Writer

Date: 2026-07-11
Issues: #482, #468
Status: Implemented locally; deployed contention baseline pending

## Objective

Prove and operate one destructive position-history recalculation writer for each normalized
portfolio/security/epoch while preserving concurrency across unrelated securities and epochs.

## Finding

Core already acquired a transaction-scoped PostgreSQL advisory lock before each position-history
delete/reinsert window and used compare-and-set epoch advancement for backdated work. Issue #482
remained open because there was no DB-backed overlapping-workflow proof, no explicit lock-wait
metric or structured wait log, and the epoch-bump counter incremented before compare-and-set so a
losing concurrent request overstated successful epoch advances.

## Implementation

- Retained the stable BLAKE2-derived signed 64-bit advisory lock key scoped to normalized
  portfolio, security, and epoch.
- Recorded lock wait duration in `position_history_replay_lock_wait_seconds` with only bounded
  `acquired` or `failed` labels.
- Added structured acquisition/failure logs with normalized key, epoch, and wait seconds.
- Moved `reprocessing_epoch_bumped_total` after successful compare-and-set.
- Added `position_recalculation_coordination_total` for bounded `epoch_advanced` and
  `coalesced/stale_epoch` decisions.
- Added combined-dashboard panels for lock-wait p95 and coordination rates. No alert threshold was
  invented without deployed baseline evidence.

## Correctness And Scalability Evidence

A PostgreSQL concurrency test holds the real advisory transaction lock in one calculation and
proves a second calculation reaches but cannot pass the same key/epoch lock. After release, both
recompute from canonical transactions and commit. Final position history contains exactly one row
per transaction with quantities `10` then `15` and cost bases `100` then `160`; no row is lost or
duplicated.

A complementary test holds that lock while a different security and the same security in a newer
epoch acquire their own locks. The single-writer control therefore does not become a portfolio-wide
or cross-epoch bottleneck. Backdated epoch compare-and-set losers are coalesced before replay or
rebuild work.

## Compatibility

No event, API, database schema, cashflow, cost, position value, replay output, or downstream
contract changed. The only behavior correction is observability truth: a failed epoch compare-and-
set no longer increments the successful epoch-bump counter.

## Validation

- Position and monitoring unit cohort: `63 passed`.
- Focused repository/telemetry cohort: `13 passed`.
- PostgreSQL concurrency module: `2 passed in 60.28s`.
- Repository-native transaction-processing contract: `29 passed in 119.32s`.
- Dashboard contract: `4 passed` plus JSON validation.
- Ruff, MyPy, architecture boundary, in-process modularity/boundary, and diff checks passed.

## Remaining Deployment Evidence

Capture lock-wait p50/p95/p99, failed lock acquisitions, coalesced stale-epoch rate, database pool
wait/utilization, and consumer retry/DLQ behavior under controlled deployed contention. Set alerts
only from a reviewed baseline. No platform skill change is required because current backend,
issue-resolution, observability, and codebase-review skills already require concurrency proof,
bounded labels, truthful metrics, and durable same-pattern guidance.
