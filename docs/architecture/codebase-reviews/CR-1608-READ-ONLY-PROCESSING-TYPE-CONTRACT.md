# CR-1608: Read-Only Processing Type Contract

## Objective

Make the transaction processing-type policy accept immutable booked transaction values without
weakening strict typing or changing control-code behavior.

## Finding

`ProcessingTypeSource` declared mutable protocol attributes even though its consumers pass frozen
`BookedTransaction` records. Strict MyPy therefore rejected position and cashflow policy calls.
The local normalization function also returned an imported value treated as `Any` while the shared
package remains outside the strict import-following boundary.

## Change

1. Declared `transaction_type` and `component_type` as read-only protocol properties.
2. Kept shared transaction control-code normalization and narrowed its local result to `str`.

## Measurable Improvement

- Removed four strict MyPy errors across processing type, position reduction, and cashflow
  processing.
- Preserved one structural policy contract that accepts both immutable and mutable sources.
- Added no casts, ignores, broad `Any`, compatibility aliases, or new modules.

## Compatibility

Transaction type normalization, FX component selection, cashflow routing, position effects, APIs,
OpenAPI, events, persistence, database structures, metrics, runtime topology, and downstream
contracts are unchanged.

## Documentation Decision

This is a type-contract correction inside an already documented domain boundary. The review ledger
changes; README, wiki, repository context, API inventory, supported features, central context, and
skills require no change for this slice. The final #779 gate slice will record the durable strict
package command in repository context.

## Validation

1. Strict MyPy passed for the policy and its position/cashflow consumers: three source files.
2. Focused processing-type, position-reducer, and cashflow-use-case tests passed: `55 passed`.
3. Scoped Ruff lint/format and repository diff checks pass before commit.

## Remaining Work

Continue #779 with read-only corporate-action and FX source protocols, typed update policies,
cost-basis annotations, infrastructure decorator typing, delivery typing, and the full-package CI
gate.
