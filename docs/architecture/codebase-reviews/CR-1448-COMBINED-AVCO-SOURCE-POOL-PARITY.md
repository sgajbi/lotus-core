# CR-1448: Combined AVCO Source/Pool Parity

Date: 2026-07-10  
Issue: #468  
Status: Hardened locally

## Objective

Prove the concrete combined transaction path selects portfolio AVCO policy and keeps pooled cost
basis, source contribution state, cashflow, position, and idempotency evidence consistent.

## Evidence

An AVCO portfolio processes, in order:

- BUY `100 @ 10` for cost `1000`;
- BUY `100 @ 12` for cost `1200`;
- SELL `50 @ 15` for proceeds `750`.

The PostgreSQL-backed path proves:

- SELL calculation policy is `SELL_AVCO_POLICY`;
- pooled COGS is `550` and realized gain is `200`;
- each source contribution remains `75` units;
- source remaining costs are `750` and `900`;
- source quantities sum to position quantity `150`;
- source base costs sum to position basis `1650`;
- cashflows are `-1000`, `-1200`, and `750`;
- position history is `100/1000`, `200/2200`, and `150/1650`;
- duplicate SELL delivery produces no repeated effects.

The scenario uses the production portfolio policy lookup, real cost/cashflow/position workflows,
shared SQLAlchemy unit of work, and PostgreSQL constraints.

## Compatibility

No route, event, schema, topic, or field name changed. This proof certifies the intentional source
value corrections in CR-1446 and CR-1447 for new processing. Historical AVCO rows still require a
governed reconciliation/backfill before current-history supportability can be claimed.

## Remaining Transaction Proof

FIFO multi-lot selection, explicit cross-currency cash legs, multi-leg corporate actions, replay,
load, and failure-recovery evidence remain required before runtime cutover.

No additional README/wiki change is required because CR-1447 already updated the source methodology
and wiki domain semantics; deployed topology remains unchanged.
