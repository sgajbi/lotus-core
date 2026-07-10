# CR-1449: Combined FIFO Multi-Lot Parity

Date: 2026-07-10  
Issue: #468  
Status: Hardened locally

## Objective

Prove the concrete combined transaction path applies FIFO selection across acquisition-source
boundaries and persists current remaining quantity and cost basis for each source.

## Evidence

A FIFO portfolio processes, in order:

- BUY `100 @ 10` for cost `1000`;
- BUY `50 @ 12` for cost `600`;
- SELL `120 @ 15` for proceeds `1800`.

The PostgreSQL-backed path proves:

- SELL calculation policy is `SELL_FIFO_POLICY`;
- FIFO COGS is `1240` and realized gain is `560`;
- the oldest source is closed with quantity and cost `0`;
- the newer source remains open with quantity `30` and cost `360`;
- source quantity and cost sums match the final position `30 / 360`;
- cashflows are `-1000`, `-600`, and `1800`;
- position history is `100/1000`, `150/1600`, and `30/360`;
- duplicate SELL delivery produces no repeated effects.

The scenario uses production portfolio policy lookup, real cost/cashflow/position workflows, the
shared SQLAlchemy unit of work, and PostgreSQL constraints.

## Compatibility

No route, event, schema, topic, or field name changed. The test certifies the current remaining
lot-state semantics introduced in CR-1447 for ordered FIFO disposal.

## Remaining Transaction Proof

Explicit cross-currency cash legs, multi-leg corporate actions, replay, load, and failure-recovery
evidence remain required before runtime cutover.

No README/wiki change is required because deployed topology is unchanged and CR-1447 already
updated lot-state methodology and wiki semantics.
