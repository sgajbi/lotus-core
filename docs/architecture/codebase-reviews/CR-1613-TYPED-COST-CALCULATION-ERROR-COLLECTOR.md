# CR-1613: Typed Cost Calculation Error Collector

## Objective

Make deterministic cost-calculation error handling fully typed and strengthen its timeline reset
and reason-aggregation guarantees.

## Finding

The collector constructor, error mutation, and reset methods lacked return annotations. Strict MyPy
therefore treated collector construction and reset calls in the application timeline as untyped,
creating six errors across domain and application layers. The focused test covered only one reason
and did not prove duplicate suppression or reset behavior.

## Change

1. Added complete `None` return annotations to collector mutation methods.
2. Reused the existing dictionary with `clear()` instead of allocating a replacement.
3. Typed the focused fixture and test inputs.
4. Added distinct-reason aggregation, duplicate suppression, and reset scenarios.

## Measurable Improvement

- Reduced the strict package baseline from 35 to 29 errors and from 12 to 10 affected files.
- Removed all six collector/timeline strict errors.
- Expanded focused collector/timeline proof to `9 passed`.
- Added no ignores, broad `Any`, compatibility aliases, new modules, or framework dependencies.

## Compatibility

Error order, duplicate suppression, reason formatting, transaction identity, timeline processing,
calculation results, APIs, OpenAPI, events, persistence, database structures, metrics, runtime
topology, and downstream contracts are unchanged.

## Documentation Decision

The review ledger changes. The legacy `tests/.../cost` ownership tree is a separate #719 repository
organization slice and is not moved in this typing commit. README, wiki, repository context, API
inventory, supported features, central context, and skills require no change here.

## Validation

1. Strict MyPy passed for the collector and the full package has no collector/timeline errors.
2. Full strict baseline: `29 errors in 10 files (179 source files checked)`.
3. Focused collector and timeline tests passed: `9 passed`.
4. Scoped Ruff lint/format, documentation catalog, and diff checks pass before commit.

## Remaining Work

Continue #779 with lot disposition, parser, calculator, infrastructure decorator, delivery/export,
and final CI-gate typing slices.
