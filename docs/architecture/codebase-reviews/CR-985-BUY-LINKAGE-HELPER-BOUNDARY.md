# CR-985: Buy Linkage Helper Boundary

Date: 2026-06-05

## Scope

Split BUY transaction metadata enrichment into focused domain helper boundaries without changing
transaction-type eligibility, generated economic event IDs, linked transaction group IDs, default
policy IDs, default policy versions, upstream value preservation, or returned event-copy behavior.

## Finding

`enrich_buy_transaction_metadata` mixed BUY eligibility, deterministic linkage ID defaults,
policy-default resolution, and update assembly in one B-ranked helper. This made a simple
transaction-domain metadata contract harder to review and keep consistent with the other
transaction metadata enrichers.

## Action

Added focused helpers for BUY transaction eligibility, BUY linkage ID resolution, BUY policy ID
resolution, and BUY metadata update assembly.

## Result

`enrich_buy_transaction_metadata` improved from `B (6)` to `A (2)`. All BUY linkage functions now
report A-ranked cyclomatic complexity, and `buy_linkage.py` remains A-ranked maintainability at
`A (73.51)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio_common\test_buy_linkage.py tests\unit\libs\portfolio_common\test_buy_validation.py tests\unit\libs\portfolio_common\test_transaction_control_code_models.py -q`
  => 14 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\transaction_domain\buy_linkage.py tests\unit\libs\portfolio_common\test_buy_linkage.py tests\unit\libs\portfolio_common\test_buy_validation.py tests\unit\libs\portfolio_common\test_transaction_control_code_models.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\transaction_domain\buy_linkage.py tests\unit\libs\portfolio_common\test_buy_linkage.py tests\unit\libs\portfolio_common\test_buy_validation.py tests\unit\libs\portfolio_common\test_transaction_control_code_models.py`
  => 4 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\transaction_domain\buy_linkage.py -s`
  => `enrich_buy_transaction_metadata` `A (2)`; all BUY linkage functions A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\transaction_domain\buy_linkage.py -s`
  => `buy_linkage.py` `A (73.51)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\transaction_domain\buy_linkage.py`
  => 44 SLOC / 24 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal transaction-domain helper refactor that
preserves BUY metadata enrichment behavior and operator-facing documentation truth.
