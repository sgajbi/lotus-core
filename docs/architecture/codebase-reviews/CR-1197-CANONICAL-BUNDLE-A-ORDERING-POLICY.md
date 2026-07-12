# CR-1197: Canonical Bundle A Ordering Policy

Date: 2026-06-30

## Objective

Address GitHub issue #683 by removing duplicate Bundle A dependency-ordering policy from the
cost-engine sorter. Event ordering and cost-engine transaction sorting should use one canonical
corporate-action ordering helper.

## Change

- Removed the cost-engine sorter's private Bundle A dependency-rank map.
- Removed the cost-engine sorter's private Bundle A target-order helper.
- Routed `TransactionSorter` through `portfolio_common.ca_bundle_a_ordering` for
  `ca_bundle_a_dependency_rank(...)` and `ca_bundle_a_target_order_key(...)`.
- Kept cash same-timestamp dependency ordering local to the sorter because it is a separate cash
  settlement processing rule.
- Added a regression test that sorts every canonical Bundle A child type and asserts the resulting
  cost-engine order is nondecreasing by the canonical dependency rank.

## Expected Improvement

There is now one authoritative Bundle A ordering policy for source-out, target-in,
cash-consideration, rights delivery, and refund sequencing. Future corporate-action type additions
must update the canonical `portfolio_common` helper, and the cost sorter will consume that policy
instead of silently drifting behind a copied map.

## Tests Added

- Cost-sorter regression coverage over all canonical Bundle A child transaction types.
- Existing sorter tests continue proving source-before-target, target sequence ordering, rights
  lifecycle ordering, normalization, and cash dependency ordering.
- Shared Bundle A ordering tests remain part of the focused validation set.

## Validation Evidence

- `python -m pytest tests/unit/services/calculators/cost_calculator_service/engine/test_sorter.py tests/unit/libs/portfolio_common/test_ca_bundle_a_ordering.py -q`
  passed with 11 tests.
- `python -m ruff check src/services/calculators/cost_calculator_service/app/cost_engine/processing/sorter.py tests/unit/services/calculators/cost_calculator_service/engine/test_sorter.py`
  passed.
- `python -m ruff format --check src/services/calculators/cost_calculator_service/app/cost_engine/processing/sorter.py tests/unit/services/calculators/cost_calculator_service/engine/test_sorter.py`
  passed.

## Downstream Compatibility

No route path, API DTO, event schema, Kafka topic, database schema, cash dependency ordering,
transaction sorting output for existing Bundle A scenarios, or cost-calculation formula changed.
The intentional implementation change is policy ownership: cost sorting now imports the canonical
Bundle A ordering helper instead of carrying a private copy.

## Documentation

- Updated RFC index evidence for RFC-077 to point at canonical ordering reuse.
- Updated the codebase review ledger.
- Updated the quality scorecard and refactor health report.
- No wiki update required because this is internal domain-policy ownership evidence and the
  repo-local wiki does not carry Bundle A ordering implementation details.

## Follow-Up

Issue #683 remains open for PR/CI/QA evidence. Future corporate-action ordering changes should add
or adjust canonical helper tests first, then prove every consumer path remains aligned.
