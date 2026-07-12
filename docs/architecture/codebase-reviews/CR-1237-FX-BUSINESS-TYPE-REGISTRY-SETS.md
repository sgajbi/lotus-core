# CR-1237 FX Business Type Registry Sets

Date: 2026-07-01

## Objective

Continue GitHub issue #474 by removing duplicated FX business transaction-type sets from
transaction-domain validation and linkage metadata enrichment.

## Change

- Derived `FX_BUSINESS_TRANSACTION_TYPES` from the canonical transaction type registry instead of
  a hard-coded local set.
- Updated FX linkage enrichment to consume the shared FX model constant instead of defining a
  second duplicate set.
- Added conformance coverage proving FX business transaction types match registry production
  booking FX lifecycle types and that linkage consumes the same object.

## Expected Improvement

FX validation and metadata enrichment now share one registry-derived source of truth. Future FX
business transaction types must be classified in the registry first and cannot drift between
validation and linkage enrichment through copy-pasted local sets.

## Tests Added

- `tests/unit/libs/portfolio-common/test_transaction_type_registry.py`
  - `test_fx_business_transaction_types_are_registry_derived_once`

## Validation Evidence

Focused validation:

- `python -m pytest tests/unit/libs/portfolio-common/test_transaction_type_registry.py tests/unit/libs/portfolio_common/test_fx_validation.py tests/unit/libs/portfolio_common/test_fx_linkage.py tests/unit/transaction_specs/test_fx_slice0_characterization.py -q`
  passed locally.

Final validation for this commit is recorded in the issue comment and review ledger.

## Downstream Compatibility

No route paths, DTOs, OpenAPI schemas, database schema, Kafka topics, event payload shapes, or
transaction type names changed. Current FX business validation and linkage behavior is preserved
for `FX_SPOT`, `FX_FORWARD`, and `FX_SWAP`; the rule source moved from duplicated local sets to the
shared registry.

## Documentation And Wiki Decision

Updated this architecture record, codebase review ledger, quality scorecard, refactor health
report, and repository context. No repo-local wiki update is required because no operator command,
route navigation, API field, or wiki workflow changed.

## Remaining Follow-Up

- Continue replacing or conformance-guarding local transaction-type sets in cost sorting,
  adjustment cash-leg generation, portfolio-flow guardrails, and validation layers.
- Add end-to-end transaction-type coverage for representative production and migration-only
  booking paths before closing issue #474.
