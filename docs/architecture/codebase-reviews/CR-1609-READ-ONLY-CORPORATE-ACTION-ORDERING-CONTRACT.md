# CR-1609: Read-Only Corporate-Action Ordering Contract

## Objective

Align deterministic corporate-action ordering with immutable booked transaction records and keep
cost-basis and position replay on one same-time restatement order.

## Finding

`CorporateActionOrderable` declared mutable fields even though position history passes frozen
`BookedTransaction` values. Strict MyPy rejected both dependency-rank and target-order-key calls.

The #996 quantity-parity fence later exposed a second ordering defect: cost replay ordered
same-time restatements by descending quantity and transaction identity, while position replay used
ingestion time and transaction identity. Two valid restatements could therefore be applied in a
different order by the two ledgers and be rejected as false quantity drift.

## Change

Declared transaction type, child sequence hint, and target instrument identity as read-only
protocol properties.

Centralized the five same-instrument quantity-restatement types under corporate-action
classification. Source acquisitions retain dependency rank 4 and same-instrument restatements use
rank 5, so a same-time source lot always exists before its quantity is restated. Both ledgers use
one shared restatement tie-break: descending governed quantity followed by stable transaction
identity. Their older tail rules remain unchanged for every other transaction family.

## Measurable Improvement

- Removed two strict MyPy errors from deterministic position-history ordering.
- Preserved one narrow structural contract for corporate-action ordering.
- Removed divergent same-time restatement ordering from cost and position replay.
- Added adverse-order domain proofs for all five restatement types and a multi-action PostgreSQL
  parity proof.
- Added no casts, ignores, mutable adapters, compatibility aliases, or new production modules.

## Compatibility

The intentional internal compatibility change is limited to equal-timestamp same-instrument
restatements: both ledgers now use the same quantity/identity order. Child sequence priority,
instrument fallback ordering, formulas, APIs, OpenAPI, events, persistence, database structures,
metrics, runtime topology, and downstream contracts are unchanged.

## Documentation Decision

The review ledger and repository context carry the reusable ordering rule. README, wiki, API
inventory, supported features, central context, and skills require no change because no public or
operator workflow changed.

## Validation

1. Strict MyPy passed for corporate-action ordering and position history.
2. Focused ordering and position-history domain tests pass before commit.
3. Scoped Ruff lint/format, documentation catalog, and diff checks pass before commit.

## Remaining Work

Continue #779 with the read-only FX source contract and the remaining typed policy, repository,
cost-basis, delivery, export, and CI-gate slices.
