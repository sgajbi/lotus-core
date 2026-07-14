# CR-1609: Read-Only Corporate-Action Ordering Contract

## Objective

Align deterministic corporate-action ordering with immutable booked transaction records while
preserving linked-leg sequencing behavior.

## Finding

`CorporateActionOrderable` declared mutable fields even though position history passes frozen
`BookedTransaction` values. Strict MyPy rejected both dependency-rank and target-order-key calls.

## Change

Declared transaction type, child sequence hint, and target instrument identity as read-only
protocol properties.

## Measurable Improvement

- Removed two strict MyPy errors from deterministic position-history ordering.
- Preserved one narrow structural contract for corporate-action ordering.
- Added no casts, ignores, mutable adapters, compatibility aliases, or new production modules.

## Compatibility

Corporate-action dependency ranks, child sequence priority, instrument fallback ordering, position
history, calculations, APIs, OpenAPI, events, persistence, database structures, metrics, runtime
topology, and downstream contracts are unchanged.

## Documentation Decision

The review ledger changes. Existing corporate-action and position-history context already owns the
policy, so README, wiki, repository context, API inventory, supported features, central context,
and skills require no change for this slice.

## Validation

1. Strict MyPy passed for corporate-action ordering and position history.
2. Focused ordering and position-history domain tests pass before commit.
3. Scoped Ruff lint/format, documentation catalog, and diff checks pass before commit.

## Remaining Work

Continue #779 with the read-only FX source contract and the remaining typed policy, repository,
cost-basis, delivery, export, and CI-gate slices.
