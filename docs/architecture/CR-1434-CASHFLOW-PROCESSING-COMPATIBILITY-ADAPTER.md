# CR-1434: Cashflow Processing Compatibility Adapter

Date: 2026-07-10  
Issue: #468  
Status: Hardened locally

## Objective

Make current cashflow processing callable inside the combined transaction unit of work while
preserving semantic idempotency, epoch fencing, rule selection, persistence, and outbox behavior.

## Change

- Added a typed cashflow stage result with explicit outcome and persisted-record count.
- Extracted a caller-owned cashflow stage that intentionally omits the old physical consumer claim
  but retains epoch fencing and the cross-topic semantic cashflow fence.
- Added a target infrastructure adapter using the shared 98-field compatibility mapper.
- Added a framework-neutral application rejection for stale epochs so the combined unit of work
  rolls back cost, cashflow, and position work together.
- Preserved the source event id, correlation id, trace context, and source topic at the adapter.

## Compatibility

The deployed cashflow consumers still execute the existing physical and semantic claims, stale
replay checks, rules, calculations, persistence, outbox writes, and commit/rollback outcomes. No
topic, group, payload, retry, DLQ, cache, image, runtime, or deployment behavior changed.

## Evidence

- Complete cashflow-calculator plus target-service unit pack: 96 passed.
- Tests cover combined-stage semantic fencing, epoch rejection, source event lineage, record counts,
  and rejection-to-rollback behavior.
- Target application/infrastructure MyPy, scoped Ruff, modularity/boundary/strict architecture
  guards, full source dead-code gate, and diff check passed.

## Same-Pattern Decision

Position processing must expose the same caller-owned staging boundary. Its epoch fence, replay
decision, replay outbox writes, and position-history writes remain correctness behavior and must not
be removed merely because consumer-owned idempotency and commit control move outward.

No README, wiki, central context, or skill change is required. Existing repository context already
requires concrete repositories, event DTOs, and framework objects to stay behind target adapters.
