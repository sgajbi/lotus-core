# CR-1615: Typed Cost Transaction Parser

## Objective

Make the raw ledger-to-cost-domain mapping boundary explicit and remove dead parser state without
changing validation or fallback behavior.

## Finding

Stub construction accepted an unparameterized `dict`, producing the final strict generic-type error
in the parser. The module also created an unused logger, and focused fixtures/tests were untyped.

## Change

1. Typed raw stub records as `dict[str, Any]`.
2. Added a complete constructor return type and clear exception variable names.
3. Removed the unused logging import and module logger.
4. Typed the focused fixtures and test signatures.

## Measurable Improvement

- Reduced the strict package baseline from 27 to 26 errors and from 9 to 8 affected files.
- Removed the package's last unparameterized collection error and one dead module dependency.
- Added no ignores, new broad `Any`, compatibility aliases, modules, or framework dependencies;
  `Any` remains confined to the intentionally raw ledger boundary.

## Compatibility

Valid transaction mapping, validation-error classification, unknown identity defaults, stub values,
error reasons, calculations, APIs, OpenAPI, events, persistence, database structures, metrics,
runtime topology, and downstream contracts are unchanged.

## Documentation Decision

The review ledger changes. The cost-test tree remains a separately bounded #719 organization
slice. README, wiki, repository context, API inventory, supported features, central context, and
skills require no change for this typing slice.

## Validation

1. The exact full-package strict command has no parser errors and reports
   `26 errors in 8 files (179 source files checked)`.
2. Valid, invalid, and multi-field fallback stub scenarios passed: `3 passed`.
3. Scoped Ruff lint/format, documentation catalog, and diff checks pass before commit.

## Remaining Work

Continue #779 with calculator, infrastructure decorator, delivery/export, and final strict-gate
slices.
