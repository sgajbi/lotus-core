# CR-1442: Combined BUY/SELL Database Parity

Date: 2026-07-10  
Issue: #468  
Status: Hardened locally

## Objective

Prove the concrete combined runtime preserves core investment transaction economics and ordered
position effects across separate booked-transaction arrivals.

## Evidence

A PostgreSQL-backed BUY `420 @ 100` followed by SELL `110 @ 110` proves:

- FIFO lot original quantity `420` and remaining open quantity `310`;
- SELL net cost `-11000` and realized gain/loss `1100`;
- BUY investment outflow `-42000` and SELL investment inflow `12100`;
- ordered position history `420 / 42000` then `310 / 31000`;
- one cashflow and one position result per event;
- two `ProcessedTransactionPersisted` and two `CashflowCalculated` compatibility events.

Each canonical transaction row is committed immediately before its own `transactions.persisted`
event. Preloading future transactions would make the position reducer correctly rebuild future
known rows, so per-portfolio delivery ordering remains a performance and predictability invariant.

## Compatibility

No deployed runtime, event, schema, cost-basis method, cashflow rule, or position algorithm changed.
The proof uses the real workflows, repositories, shared UoW, and PostgreSQL constraints.

## Remaining BUY/SELL Proof

Fees, FX conversion, full disposal, multi-lot selection, AVCO, cross-currency cash legs, and
multi-leg corporate-action behavior remain required before runtime cutover.

No README/wiki change is required because deployed behavior is unchanged.
