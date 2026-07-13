# CR-1565 Corporate Action Policy Ownership

Date: 2026-07-14

## Objective

Move corporate-action classification and linked-leg ordering out of the shared library and remove
an unused event-level ordering surface so calculation policy has one domain owner.

## Findings

- `portfolio_common` contained Bundle-A classification and ordering policy used by one runtime
  capability plus tests.
- `portfolio_common.events.transaction_event_ordering_key` had no runtime callers and duplicated
  ordering already performed over canonical booked transactions in cost and position processing.
- `CostBasisTransaction` accepted sequence and target-instrument metadata as undeclared dynamic
  extras, obscuring the ordering contract.

## Change

- Moved classification and ordering to
  `app/domain/transaction/corporate_action/classification.py` and `ordering.py`.
- Replaced implementation-bundle names with basis-transfer and corporate-action domain names while
  preserving durable evidence reason codes and transaction codes.
- Declared `child_sequence_hint` and `target_instrument_id` on `CostBasisTransaction` with explicit
  integer validation.
- Removed the unused event ordering helper and its duplicate tests; retained event timestamp
  normalization tests and owner-level cost/position ordering tests.
- Updated RFC-079, RFC-080, the RFC index, risk matrix, context, and historical review supersession
  notes to current ownership truth.

## Compatibility

No API, event payload, database, topic, image, deployment, or persisted transaction-code behavior
changed. The removed Python helper was undocumented and had no repository runtime callers.

## Validation

- `53` affected event, classification, validation, reconciliation, ordering, model, and position
  tests passed.
- `33` structure and registry conformance tests passed.
- Focused MyPy, Ruff, domain-layer, dependency-inversion, and capability-catalog guards passed.

## Documentation Decision

README and wiki do not expose implementation module locations, so no README or wiki change was
required. RFC, architecture ledger, repository context, and risk-matrix truth changed and were
updated in this slice.
