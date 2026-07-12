# CR-1435: Position Processing Compatibility Adapter

Date: 2026-07-10  
Issue: #468  
Status: Hardened locally

## Objective

Make existing position and backdated-replay processing callable through the combined application
port without coupling the new use case to Kafka consumers or hiding the calculation outcome.

## Change

- Added an immutable position calculation result with persisted-position count and replay-queued
  status.
- Made stale-epoch, normal recalculation, backdated replay, and replay-race paths return explicit
  results while preserving their existing writes and exits.
- Added a target infrastructure adapter that maps the domain transaction through the shared
  compatibility mapper and delegates to the current position policy with caller-owned repositories.
- Preserved correlation and trace context through the event compatibility boundary.

## Compatibility

The deployed position consumers continue to own their current idempotency transaction and invoke
the same position calculator. Existing epoch fencing, locking, position-history replacement,
watermark rearming, epoch bump, and replay outbox behavior are unchanged. No topic, group, payload,
retry, DLQ, image, runtime, or deployment behavior changed.

## Evidence

- Complete position-calculator plus target-service unit pack: 102 passed.
- Normal processing reports one staged record, stale epochs report no work, and backdated replay
  reports the queued outcome while retaining the two-event replay proof.
- Focused MyPy/Ruff, modularity/boundary/strict architecture guards, full source dead-code gate, and
  diff check passed.

## Same-Pattern Decision

Cost, cashflow, and position now expose caller-owned stages behind target infrastructure adapters.
The next slice must instantiate all three from one SQLAlchemy session and prove one commit or one
rollback; adapter availability alone is not runtime consolidation.

No README, wiki, central context, or skill change is required. The existing architecture decision,
repository context, and modularity catalog already define this migration sequence and package rule.
