# CR-1486: Cash-In-Lieu Fractional Ledger Parity

Date: 2026-07-10
Issue: #468
Status: Hardened locally; deployed cutover evidence pending

## Objective

Model cash-in-lieu as an auditable fractional security disposal plus linked cash-account settlement,
including exact local/base basis, realized capital/FX/total P&L, position state, flow balance,
effective-dated FX, duplicate behavior, and atomic failure.

## Findings

1. `CASH_IN_LIEU` used generic `SellStrategy`. It consumed quantity and calculated total gain but
   ignored source-owned allocated fractional basis and did not populate capital/FX/total P&L
   components.
2. The seeded cashflow rule classified cash-in-lieu as `INCOME`, conflicting with the governed
   `POSITION_CASH_IN_LIEU_OUT` synthetic transfer and incorrectly making capital disposal eligible
   for income-since-inception.
3. `ADJUSTMENT` cash legs bypassed the cost engine, leaving cross-currency settlement FX and base
   cost null. Cash positions could therefore carry local cash amount as base basis.

## Change

- Added dedicated `CashInLieuStrategy` requiring positive fractional quantity/proceeds and explicit
  allocated local/base basis.
- Reused the pure corporate-action cash economics policy to validate capital, FX, and total P&L.
- Required consumed lot quantity and local/base basis to equal the fractional allocation exactly.
- Added Alembic head `c107b2c3d4ec`, changing `CASH_IN_LIEU` from `INCOME` to position-level,
  non-portfolio `TRANSFER` with symmetric downgrade.
- Added direction-aware `AdjustmentStrategy` and removed the adjustment bypass so cash legs receive
  normal latest-on-or-before FX enrichment and persist signed local/base cost.
- Added a combined PostgreSQL EUR/SGD product-plus-cash ledger scenario with duplicate proof.

## Ledger Invariants

For the implemented cross-currency scenario:

- fractional quantity disposed: `0.5`;
- allocated basis: EUR `50`, SGD `67.5`;
- net proceeds: EUR `60`, SGD `81`;
- realized total P&L: EUR `10`, SGD `13.5`;
- base P&L components: capital `10` plus FX `3.5`;
- product position flow: EUR `-60`;
- linked cash settlement flow: EUR `+60`;
- linked flow sum: `0`;
- surviving target position: quantity `10`, basis EUR `1000` / SGD `1350`;
- cash position: quantity/basis EUR `60`, base basis SGD `81`.

## Compatibility And Intentional Change

API fields and event shapes remain unchanged. Cash-in-lieu now fails closed when allocated basis is
missing or disagrees with consumed lot state. Its cashflow classification intentionally changes from
`INCOME` to `TRANSFER`; downstream income-since-inception must no longer count it as income.
Cross-currency adjustments now persist authoritative FX and signed base cost instead of null/base
fallback values. Topics, groups, linked cash-leg structure, and duplicate semantics are preserved.

No README change is required: repository entry points, supported service topology, and operator
commands are unchanged. The behavior truth is recorded in the architecture ledger, schema catalog,
repository context, and cost/cashflow wiki source.

## Validation

- cost and target unit packs: `377 passed`;
- dedicated cost/AVCO engine pack: `106 passed`;
- branch-built PostgreSQL cash-in-lieu ledger path: `1 passed in 55.29 seconds`;
- database cashflow-rule contract: `1 passed in 53.59 seconds`;
- manifest-owned combined PostgreSQL contract: `26 passed in 113.06 seconds`;
- migration SQL contract passed with one head at `c107b2c3d4ec`;
- MyPy, strict architecture, full Ruff lint/format, and docs/wiki gates passed.

Deployed throughput, support diagnostics, and downstream cutover evidence remain open under #468.
