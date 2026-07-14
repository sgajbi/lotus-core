# CR-1612: Typed FX Linkage Update

## Objective

Make deterministic FX linkage updates explicit and type-safe while reducing policy fragmentation.

## Finding

FX metadata enrichment composed four broad `dict[str, object]` helpers and expanded the result into
a frozen booked transaction. Strict MyPy emitted ten keyword-type errors plus two redundant-cast
errors, and the complete linkage contract was spread across multiple update functions.

## Change

1. Added one complete `FxMetadataUpdate` `TypedDict`.
2. Built linkage, policy, instrument, lifecycle, and processing-mode fields in one explicit mapping.
3. Removed four broad dictionary-composition helpers.
4. Replaced redundant casts with concrete string normalization at isolated source boundaries.

## Measurable Improvement

- Reduced the strict package baseline from 47 to 35 errors and from 13 to 12 affected files.
- Removed all twelve FX linkage typing errors.
- Reduced the linkage policy by 39 net lines (`26` added, `65` removed).
- Added no ignores, broad `Any`, compatibility aliases, new modules, or framework dependencies.

## Compatibility

Economic event identity, linked group identity, policy defaults, component identity, swap grouping,
contract identity, cash-leg role, contract instrument identity, lifecycle transaction links,
processing modes, APIs, OpenAPI, events, persistence, database structures, metrics, runtime topology,
and downstream contracts are unchanged.

## Documentation Decision

The review ledger changes. Existing FX conformance and repository context already document linkage
ownership, so README, wiki, API inventory, supported features, central context, and skills require
no change for this slice.

## Validation

1. Strict MyPy passed for the FX linkage policy.
2. Full strict baseline: `35 errors in 12 files (179 source files checked)`.
3. Deterministic forward, swap, cash-leg, upstream-value, and contract-close scenarios passed:
   `5 passed`.
4. Scoped Ruff lint/format, documentation catalog, and diff checks pass before commit.

## Remaining Work

Continue #779 with cost-basis annotations, infrastructure decorator typing, delivery/export typing,
and the final strict package gate.
