# Portfolio Flow Bundle Slice 3 Calculator Harmonization

## Objective

Align position-calculator behavior with RFC-074 and transaction-spec semantics for portfolio-level flows.

## Implemented Changes

1. Updated position calculator behavior:
 - `DEPOSIT`, `WITHDRAWAL`, `FEE`, `TAX` no longer mutate security position quantity/cost.
 - `TRANSFER_IN` and `TRANSFER_OUT` mutate position only when `transfer_quantity > 0`.
 - zero-quantity transfers are treated as cash-only transfer semantics in position logic.
2. Cost basis handling for security transfers:
 - prefers `net_cost` / `net_cost_local` when provided.
 - falls back to gross-sign behavior when transfer quantity exists and net cost is absent.
3. Updated bundle characterization tests to canonicalized semantics.

## Behavioral Impact

1. Portfolio cash-only flow types no longer create artificial security position drift.
2. Security transfers continue to update quantity and transferred basis.
3. Cash-only transfers no longer affect security holdings state.

## Follow-On Work

1. Slice 4: query and observability contract hardening for the bundle.
