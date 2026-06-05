# CR-990: CA Bundle A Dependency Ordering Helper Boundary

Date: 2026-06-05

## Scope

Split CA Bundle A dependency rank policy into explicit rank groups without changing source-out,
target-in, cash-consideration, rights-stage, refund, target ordering, or unknown-type fallback
behavior.

## Finding

`ca_bundle_a_dependency_rank` mixed normalized transaction-type lookup with repeated branch checks
for source-out, target-in, cash-consideration, rights-stage, and refund ranks in one B-ranked
helper. This made corporate-action dependency ordering harder to review as the Bundle A transaction
surface grew.

## Action

Added explicit rank-type sets and a deterministic dependency-rank map so the public helper now
normalizes the transaction type and performs a single lookup with the existing unknown fallback.

## Result

`ca_bundle_a_dependency_rank` improved from `B (8)` to `A (1)`. The CA Bundle A ordering module
now reports A-ranked cyclomatic complexity for every function and remains A-ranked maintainability
at `A (89.61)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio_common\test_ca_bundle_a_ordering.py tests\unit\libs\portfolio_common\test_ca_bundle_a_reconciliation.py tests\unit\libs\portfolio_common\test_ca_bundle_a_validation.py -q`
  => 14 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\ca_bundle_a_ordering.py tests\unit\libs\portfolio_common\test_ca_bundle_a_ordering.py tests\unit\libs\portfolio_common\test_ca_bundle_a_reconciliation.py tests\unit\libs\portfolio_common\test_ca_bundle_a_validation.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\ca_bundle_a_ordering.py tests\unit\libs\portfolio_common\test_ca_bundle_a_ordering.py tests\unit\libs\portfolio_common\test_ca_bundle_a_reconciliation.py tests\unit\libs\portfolio_common\test_ca_bundle_a_validation.py`
  => 4 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\ca_bundle_a_ordering.py -s`
  => `ca_bundle_a_dependency_rank` `A (1)` and `ca_bundle_a_target_order_key` `A (3)`
- `python -m radon mi src\libs\portfolio-common\portfolio_common\ca_bundle_a_ordering.py -s`
  => `ca_bundle_a_ordering.py` `A (89.61)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\ca_bundle_a_ordering.py`
  => 38 SLOC / 17 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal CA Bundle A ordering helper refactor that
preserves dependency ordering behavior and operator-facing documentation truth.
