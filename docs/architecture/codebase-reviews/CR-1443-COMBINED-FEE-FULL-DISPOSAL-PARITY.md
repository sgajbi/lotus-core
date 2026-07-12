# CR-1443: Combined Fee And Full-Disposal Parity

Date: 2026-07-10  
Issue: #468  
Status: Hardened locally

## Objective

Prove that the concrete combined transaction path preserves fee economics across cost, cashflow,
lot, and position ownership and reaches an exact closed state after a full disposal.

## Evidence

A PostgreSQL-backed BUY `15 @ 100` with a `7.50` fee followed by a full SELL `15 @ 110` with a
`5.00` fee proves:

- BUY book cost and lot cost basis `1507.50`;
- SELL cost relieved `-1507.50` and realized gain/loss `137.50`;
- source-owned brokerage rows `7.50` and `5.00` on their respective transactions;
- investment cashflows `-1507.50` and `1645.00`;
- position history `15 / 1507.50` followed by exact `0 / 0`;
- lot open quantity reduced from `15` to exact `0`;
- duplicate SELL delivery produces no repeated module effects.

The proof uses separate booked-transaction arrivals and the concrete workflows, repositories,
combined idempotency fence, shared SQLAlchemy unit of work, and PostgreSQL constraints.

## Compatibility

No deployed runtime, event contract, schema, cost-basis method, cashflow rule, or position algorithm
changed. `transaction_costs`, position-lot state, cashflows, and position history remain distinct
domain persistence structures because they encode separate audit and calculation invariants.

## Remaining Transaction Proof

FX conversion, AVCO, multi-lot selection, cross-currency cash legs, multi-leg corporate actions,
replay, load, and failure-recovery evidence remain required before runtime cutover.

No README/wiki change is required because deployed behavior is unchanged.
