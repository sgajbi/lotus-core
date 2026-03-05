# Portfolio Flow Bundle Slice 5 Regression Suite and CI Wiring

## Objective

Create a dedicated RFC-074 contract test lane and enforce it in local and CI workflows.

## Implemented Changes

1. Added manifest suite:
 - `transaction-portfolio-flow-bundle-contract`
 - Alias: `portfolio-flow-bundle-rfc`
2. Added Make targets:
 - `test-transaction-portfolio-flow-bundle-contract`
 - `test-portfolio-flow-bundle-rfc`
3. Added CI matrix entry in `.github/workflows/ci.yml`:
 - `transaction-portfolio-flow-bundle-contract`
4. Suite coverage includes:
 - transaction-domain guardrails
 - portfolio-flow bundle unit semantics
 - position/cashflow/cost consumer behavior
 - query core snapshot and simulation behavior

## Enforcement Outcome

Any PR run now executes the dedicated RFC-074 portfolio-flow bundle contract suite as part of the standard test matrix.
