# Portfolio Flow Bundle Slice 2 Classification Alignment

## Objective

Align portfolio-flow classification rules for the RFC-074 bundle, with explicit closure for `TAX`.

## Implemented Changes

1. Added migration `a9c4d2e8f1b7_feat_align_tax_cashflow_rule_portfolio_flow.py`.
2. Migration update:
 - sets `cashflow_rules.is_portfolio_flow = TRUE` for `transaction_type='TAX'`.
3. Downgrade path:
 - restores `is_portfolio_flow = FALSE` for `TAX`.
4. Added regression test asserting canonical TAX cashflow classification semantics in calculator output.

## Behavioral Impact

1. `TAX` is now consistently modeled as a portfolio-level flow in rule state.
2. Downstream calculators that consume persisted rule flags now receive canonical portfolio-flow classification for TAX.
3. This intentionally supersedes the Slice 0 characterization baseline that captured pre-alignment state.

## Follow-On Work

1. Slice 3: harmonize position and cost calculator semantics for portfolio-flow bundle transaction types.
