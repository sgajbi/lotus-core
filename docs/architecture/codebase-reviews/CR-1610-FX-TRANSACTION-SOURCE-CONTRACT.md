# CR-1610: FX Transaction Source Contract

## Objective

Give canonical FX conversion a clearly owned read-only source contract that accepts immutable
booked transaction values without expanding the FX model module.

## Finding

The broad `FxTransactionSource` protocol lived inside `models.py` and declared every field as
mutable. Strict MyPy rejected the frozen `BookedTransaction` used by baseline FX processing. The
contract's location also made the canonical value module responsible for both value behavior and a
large structural input boundary.

## Change

1. Moved the protocol to the domain-owned `fx/transaction_source.py` module.
2. Declared every source field as a read-only property.
3. Kept `FxCanonicalTransaction.from_transaction(...)` and all field mapping unchanged.
4. Added a package-ownership test for the new source contract.

## Measurable Improvement

- Reduced the strict package baseline from 58 to 57 errors.
- Reduced `models.py` by the broad protocol declaration and gave the contract a durable domain name.
- Added one reintroduction/ownership assertion.
- Added no type ignores, broad `Any`, compatibility aliases, framework dependencies, or mutable
  adapters.

The remaining legacy `CostBasisTransaction` mismatch stays visible for the separately bounded
cost-basis annotation slice.

## Compatibility

FX normalization, validation, linkage, contract-instrument construction, amounts, currencies,
rates, realized P&L, APIs, OpenAPI, events, persistence, database structures, metrics, runtime
topology, and downstream contracts are unchanged.

## Documentation Decision

The codebase-review ledger changes. The existing repository context already assigns FX domain
policy to this package, so README, wiki, API inventory, supported features, central context, and
skills require no change for this slice.

## Validation

1. Strict package baseline measured `57 errors in 14 files (179 source files checked)`.
2. FX contract-instrument, baseline-processing, package ownership, and cost-calculator behavior
   passed: `82 passed`.
3. The package ownership assertion passes with the focused FX structure suite.
4. Scoped Ruff lint/format, documentation catalog, and diff checks pass before commit.

## Remaining Work

Continue #779 with typed FX update policies, cost-basis source/annotation cleanup, infrastructure
decorator typing, delivery/export typing, and the full-package strict CI gate.
