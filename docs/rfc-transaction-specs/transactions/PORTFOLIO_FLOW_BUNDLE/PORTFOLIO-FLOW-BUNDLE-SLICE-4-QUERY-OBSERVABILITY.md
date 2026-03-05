# Portfolio Flow Bundle Slice 4 Query and Observability Hardening

## Objective

Align query-service projection behavior with RFC-074 portfolio-level flow semantics.

## Implemented Changes

1. Updated quantity-effect logic in:
 - `CoreSnapshotService._change_quantity_effect`
 - `SimulationService._change_quantity_effect`
2. Query projection rules now treat only these as position-quantity mutators:
 - positive: `BUY`, `TRANSFER_IN`
 - negative: `SELL`, `TRANSFER_OUT`
3. `DEPOSIT`, `WITHDRAWAL`, `FEE`, and `TAX` now produce zero position-quantity delta in projected views.
4. Added/updated query service unit tests covering:
 - transfer quantity handling
 - zero quantity effect for portfolio-level cash/charge types
 - explicit `FEE` and `TAX` behavior

## Behavioral Impact

1. Simulation and core snapshot projections no longer drift security quantity due to portfolio-level flows.
2. Query-side position projections are now consistent with calculator semantics introduced in Slice 3.
