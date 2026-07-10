# CR-1444: Combined Effective-Dated FX Parity

Date: 2026-07-10  
Issue: #468  
Status: Hardened locally

## Objective

Prove deterministic effective-dated FX selection and consistent local/base currency persistence
through the concrete combined transaction path.

## Evidence

A PostgreSQL-backed EUR BUY `10 @ 100` with a `10.00` fee in an SGD portfolio includes EUR/SGD
rates dated May 1 (`1.40`), May 9 (`1.45`), and May 11 (`1.50`) for a May 10 transaction. The path
proves:

- latest-on-or-before selection of `1.45`, excluding the future rate;
- local net cost and lot basis `1010.00` EUR;
- base net cost, lot basis, and position basis `1464.50` SGD;
- brokerage fee `10.00` EUR;
- investment cashflow `-1010.00` EUR;
- one cashflow and one position result from the combined unit of work.

The proof uses the production FX repository query, concrete calculation workflows, one shared
SQLAlchemy unit of work, and PostgreSQL constraints.

## Compatibility

No deployed runtime, FX quote convention, event contract, schema, calculation policy, cashflow rule,
or position algorithm changed. The test confirms current source-owned effective-date behavior.

## Remaining Transaction Proof

AVCO, multi-lot selection, explicit cross-currency cash legs, multi-leg corporate actions, replay,
load, and failure-recovery evidence remain required before runtime cutover. Shared combined test
fixtures should be extracted before adding those variants so the test layout stays easy to navigate.

No README/wiki change is required because deployed behavior is unchanged.
