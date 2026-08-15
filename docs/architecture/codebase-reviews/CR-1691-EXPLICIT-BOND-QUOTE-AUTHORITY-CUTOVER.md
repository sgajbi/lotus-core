# CR-1691: Explicit Bond Quote-Authority Cutover

## Objective

Close the remaining #451 ambiguity by ensuring every successful non-flat bond valuation and its
independent reconciliation derive quote representation from explicit, effective-dated authority.

## Finding

The scoped valuation path already resolved tenant/legal-book/security policy assignments and
source-lineaged market-price facts. Two unscoped compatibility consumers still called a shared
helper that inferred unit-price versus percent-of-principal treatment from price, quantity, and
average cost. Thresholds below 200 and above average cost 500 selected 1, 10, or 100 multipliers.
Those values cannot establish economic representation for unusual denominations, migrated unit
prices, partial lots, or structured fixed-income instruments.

## Change

- Deleted the magnitude-based helper and all 1/10/100 inference branches.
- Kept quote-independent flat positions and unscoped non-bond unit-price behavior compatible.
- Made a non-flat unscoped bond job persist `FAILED` with the stable reason
  `bond valuation requires explicit quote-convention authority` and without an invented receipt.
- Made financial reconciliation emit the blocking `missing_bond_quote_authority` finding for a
  missing or `LEGACY_UNSCOPED` bond receipt. The finding is owned by `VALUATION_OPERATIONS` and
  carries repair recommendation `ASSIGN_VALUATION_QUOTE_POLICY`.
- Added `bond-quote-authority-guard` to the standard lint lane. Mutation tests reject restoration of
  the deleted helper names and removal of the explicit authority fence from either production
  consumer.

## Same-Pattern Review

Repository-wide import and symbol searches found two production consumers: position valuation and
financial reconciliation. Both are cut over in this change. Historical review documents that
describe the former helper remain historical evidence; current methodology, repository context,
and operator wiki truth now state that the fallback is retired.

No separate defect was discovered. Exact-scope assignment resolution, price-source resolution,
and reconciliation receipt loading retain their existing bounded repository behavior. This slice
adds no query, loop, cache, topic, partition, dependency, or runtime service.

## Compatibility

Assigned unit-price and supported percent-of-principal policies keep their existing registry-owned
formula, Decimal precision, rounding, FX, source lineage, and calculation receipt behavior. Public
API, OpenAPI, event, database, and migration shapes are unchanged. The intentional safety change is
limited to ambiguous unscoped non-flat bonds: fail closed rather than infer quote representation.

Broader accrued-income source wiring, factor-adjusted or supplied current principal, listed-contract
multiplier/deliverable evidence, and mixed-product capacity certification remain owned by #788.

## Validation

- warning-strict quote-authority, valuation, consumer, reconciliation, mapping, and mutation tests;
- repository-native bond quote authority guard;
- Ruff lint/format, MyPy, architecture, calculation-policy, documentation, and wiki gates;
- protected PR and exact-main evidence are recorded on #451 after completion.

## Documentation Decision

The valuation methodology, repository context, and Valuation/Financial-Reconciliation wiki sources
change because calculation and operator remediation truth changed. README, OpenAPI, events,
database catalog, migrations, and supported-feature claims do not change because their contracts
did not change.
