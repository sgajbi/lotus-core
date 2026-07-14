# CR-1611: Typed FX Baseline Processing Update

## Objective

Preserve the shared FX cost-engine mapping contract while making baseline cost and realized-P&L
updates explicit, type-safe, and simpler.

## Finding

Baseline processing assembled broad `dict[str, object]` fragments and expanded them into frozen
`BookedTransaction` records. Strict MyPy emitted ten incompatible keyword errors, and five small
dictionary helpers obscured the complete set of calculated fields.

## Change

1. Added `FxBaselineProcessingUpdate`, a complete `TypedDict` for the existing runtime mapping.
2. Built all cost and P&L fields in one explicit return value.
3. Replaced fragmented zero/upstream dictionary helpers with one typed P&L value resolver.
4. Added a direct cost-engine mapping contract test.

## Measurable Improvement

- Reduced the strict package baseline from 57 to 47 errors and from 14 to 13 affected files.
- Removed all ten baseline `dataclasses.replace` typing errors.
- Preserved the exported helper's runtime `dict` shape and cost-engine `.items()` consumption.
- Removed duplicate dictionary composition without adding ignores, casts, broad `Any`, or a new
  compatibility surface.

## Compatibility

`NONE` zeroing, `UPSTREAM_PROVIDED` totals, unsupported-mode rejection, cost field values, mapping
keys, FX validation, APIs, OpenAPI, events, persistence, database structures, metrics, runtime
topology, and downstream contracts are unchanged.

## Documentation Decision

The review ledger changes. Existing FX conformance and repository context already describe the
baseline modes, so README, wiki, API inventory, supported features, central context, and skills
require no change for this slice.

## Validation

1. Full strict baseline: `47 errors in 13 files (179 source files checked)`.
2. Baseline-processing and cost-calculator behavior pass: `79 passed`.
3. Scoped Ruff lint/format, documentation catalog, and diff checks pass before commit.

## Remaining Work

Continue #779 with typed FX linkage updates, cost-basis annotations, infrastructure decorator
typing, delivery/export typing, and the final strict package gate.
