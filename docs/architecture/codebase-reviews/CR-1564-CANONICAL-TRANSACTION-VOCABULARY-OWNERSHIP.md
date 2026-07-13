# CR-1564 Canonical Transaction Vocabulary Ownership

Date: 2026-07-14

## Objective

Remove service-local transaction vocabularies and repeated registry projections so transaction
processing, simulation, and query behavior follow one governed source without adding runtime
coupling.

## Findings

- The cost-basis domain maintained a second 42-member `TransactionType` enum beside the canonical
  registry.
- Query Service and Query Control Plane each implemented the same production position-effect
  registry scan and published four identical code sets.
- Transaction capability tools were split across generic `generators`, `quality`, and test roots
  despite one transaction-processing owner.

## Change

- Deleted the cost-domain enum and changed strategy selection and tests to canonical normalized
  transaction codes.
- Added one immutable position-effect selector to the canonical registry and reused it from both
  query consumers.
- Moved capability generation, validation, and tests under mirrored transaction-processing
  packages with action-oriented filenames.
- Added structural and conformance tests that prevent a duplicate enum, selector drift, or stale
  generator command from returning.

## Compatibility

No API, event, database, topic, image, deployment, or persisted transaction-code contract changed.
Registered but production-disabled transaction types now receive the canonical not-allowed
diagnostic instead of being misclassified as unknown inside cost calculation.

## Validation

- `112` cost, disposition, registry, and transaction-spec tests passed.
- `78` registry, Query Service position-effect, and QCP simulation tests passed.
- `6` transaction capability validator tests passed.
- Focused Ruff, formatting, MyPy, catalog, front-door, and wiki/docs gates passed.

## Remaining Policy Tables

Cost ordering and position-reducer sets remain local only where they encode domain ordering,
same-instrument, transfer-basis, or generated-leg policy beyond registry classification. Each must
remain registry-conformant and should be centralized only after behavior-equivalence proof.
