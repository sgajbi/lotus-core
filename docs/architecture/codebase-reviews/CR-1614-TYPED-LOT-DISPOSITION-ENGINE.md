# CR-1614: Typed Lot Disposition Engine

## Objective

Complete lot-disposition mutation contracts and remove dead logging state without changing FIFO or
AVCO strategy behavior.

## Finding

Buy-lot addition and initial-lot restoration lacked return annotations, producing two strict
package errors. The module also created an unused logger, and focused test functions retained
untyped signatures.

## Change

1. Added complete `None` return types to engine construction and mutation methods.
2. Removed the unused logging import and module logger.
3. Added explicit return and mock parameter types to the focused delegation tests.

## Measurable Improvement

- Reduced the strict package baseline from 29 to 27 errors and from 10 to 9 affected files.
- Removed both lot-disposition strict errors and one dead module dependency.
- Added no ignores, broad `Any`, compatibility aliases, new modules, or framework dependencies.

## Compatibility

Buy filtering, quantity normalization, sell consumption, transfer-basis delegation, initial-lot
selection, open-lot restoration, FIFO/AVCO behavior, calculations, APIs, OpenAPI, events,
persistence, database structures, metrics, runtime topology, and downstream contracts are
unchanged.

## Documentation Decision

The review ledger changes. The legacy cost-test tree remains a separately bounded #719
organization slice. README, wiki, repository context, API inventory, supported features, central
context, and skills require no change for this typing slice.

## Validation

1. The exact full-package strict command has no lot-disposition errors and reports
   `27 errors in 9 files (179 source files checked)`.
2. Focused delegation, quantity-normalization, filtering, and restore tests passed: `7 passed`.
3. Scoped Ruff lint/format, documentation catalog, and diff checks pass before commit.

## Remaining Work

Continue #779 with parser, calculator, infrastructure decorator, delivery/export, and final
strict-gate slices.
