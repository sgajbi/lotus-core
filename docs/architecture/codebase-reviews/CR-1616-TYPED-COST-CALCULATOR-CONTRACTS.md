# CR-1616: Typed Cost Calculator Contracts

## Objective

Complete cost-calculator callback and mutation typing without mixing in the separate dynamic FX
source validation decision.

## Finding

Three invariant helpers accepted untyped callbacks, the sell-proceeds helper retained a redundant
`Decimal` cast, and the calculator mutation entry point omitted its return type. These created five
strict errors across otherwise typed cost policies.

## Change

1. Typed invariant callbacks with the existing `InvariantErrorAdder` domain contract.
2. Removed the redundant sell-proceeds cast.
3. Declared `calculate_transaction_costs(...)` as an in-place `None` mutation.

## Measurable Improvement

- Reduced the strict package baseline from 26 to 21 errors.
- Removed five calculator typing errors while keeping the dynamic FX source mismatch visible for a
  separately tested fail-closed slice.
- Added no ignores, broad `Any`, compatibility aliases, new modules, or framework dependencies.

## Compatibility

Price validation, zero-quantity/cost/P&L invariants, sell proceeds, strategy dispatch, transaction
mutation, calculations, APIs, OpenAPI, events, persistence, database structures, metrics, runtime
topology, and downstream contracts are unchanged.

## Documentation Decision

The review ledger changes. Existing cost-basis standards and context already own these policies;
README, wiki, repository context, API inventory, supported features, central context, and skills
require no change for this typing slice.

## Validation

1. Exact full-package strict baseline: `21 errors in 8 files (179 source files checked)`; only the
   separately scoped FX source mismatch remains in this calculator.
2. Complete focused cost-calculator suite passed: `75 passed`.
3. Scoped Ruff lint/format, documentation catalog, and diff checks pass before commit.

## Remaining Work

Add the fail-closed dynamic FX source contract, then continue #779 with infrastructure decorators,
delivery/export typing, and the final strict package gate.
