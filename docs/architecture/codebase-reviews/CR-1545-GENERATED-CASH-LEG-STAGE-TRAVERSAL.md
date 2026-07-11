# CR-1545: Generated Settlement Cash-Leg Stage Traversal

Date: 2026-07-12
Issue: #468
Status: Reconciled candidate; release proof pending

## Objective

Ensure every transaction emitted by the cost stage, including an auto-generated settlement cash
leg, traverses the unified position and cashflow stages exactly once inside the same database
transaction.

## Finding

The historical final backlog commit fixed a real omission: cashflow processing had received only
the original booking instead of every cost-stage output. During reconciliation, however, the
current use case already contained a stronger epoch-aware traversal after position processing.
Applying the historical loop as written would process each emitted leg through cashflow twice.

Generated settlement legs also remain part of the position-linked transaction group. They are
therefore position flows, while `is_portfolio_flow=false` distinguishes them from external funding
or withdrawal.

## Reconciliation Decision

- Keep cost as the source of the complete ordered transaction-leg set.
- Process every emitted leg through position before deriving cashflow-stage work.
- Use the existing cashflow-stage selection policy to include normal legs and rebuilt epochs once.
- Commit cost, position, cashflow, semantic idempotency, and compatibility outbox effects atomically.
- Reject a second pre-position cashflow loop because it duplicates persistence and observations.

## Compatibility

No API, event, topic, database schema, or downstream response contract changes. The decision
preserves linked product and settlement evidence while preventing duplicate cashflow effects.

## Validation Evidence

- Focused use-case ordering and observation tests: `13 passed`.
- PostgreSQL auto-generated buy product/settlement traversal: `1 passed`.
- Ruff lint and formatting checks for the implementation and focused tests: passed.
- Aggregate transaction and release cohorts remain required before merged-main closure.

## Documentation Decision

Repository engineering context and the authored cashflow wiki now state the generated-leg rule.
No platform-wide skill change is needed: the existing transaction-stage ownership and single-unit-
of-work guidance already governs the pattern.
