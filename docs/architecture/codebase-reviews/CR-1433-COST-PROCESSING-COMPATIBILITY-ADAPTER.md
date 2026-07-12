# CR-1433: Cost Processing Compatibility Adapter

Date: 2026-07-10  
Issue: #468  
Status: Hardened locally

## Objective

Make the existing cost calculation callable by the combined transaction use case without giving
the cost consumer ownership of idempotency or the database transaction.

## Change

- Split the current cost processor into an idempotent consumer entry point and a caller-owned
  `stage_valid_event` operation.
- Added a typed stage result containing every emitted transaction leg and the instrument update
  count.
- Added an infrastructure compatibility adapter that maps `BookedTransaction` to the governed
  event contract, runs the existing policy, and maps all processed legs back to domain models.
- Kept all legacy calculator and event-model imports inside target infrastructure.

## Compatibility

The existing cost consumer still claims the same `cost-calculator` idempotency fence and runs the
same repository, calculation, persistence, and outbox methods in the same transaction. No topic,
group, payload, retry, DLQ, image, runtime, or deployment behavior changed.

## Evidence

- Cost consumer, stage extraction, adapter mapping, and import-confinement tests: 40 passed.
- Complete cost-calculator plus target-service unit pack: 173 passed.
- Focused MyPy, Ruff, in-process boundary, and strict architecture guards passed.
- Full source dead-code gate passed; protocol-only exit parameters use intentionally ignored names.
- Existing consumer tests now assert the emitted-leg and instrument-count result without changing
  current side-effect assertions.

## Same-Pattern Decision

Cashflow and position need the same caller-owned staging boundary before the combined unit of work
can be wired. Their existing consumer-owned commits and idempotency fences must not be called from
the new application use case.

No README, wiki, central context, or skill change is required. The repository architecture context
already requires compatibility event models and concrete repositories to remain behind target
infrastructure adapters.
