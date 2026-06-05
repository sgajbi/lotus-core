# CR-986: Sell Linkage Helper Boundary

Date: 2026-06-05

## Scope

Split SELL transaction metadata enrichment into focused domain helper boundaries without changing
transaction-type eligibility, generated economic event IDs, linked transaction group IDs, FIFO
versus AVCO policy selection, default policy versions, upstream value preservation, unsupported
cost-basis behavior, or returned event-copy behavior.

## Finding

`enrich_sell_transaction_metadata` mixed SELL eligibility, deterministic linkage ID defaults,
cost-basis policy selection, policy-default resolution, and update assembly in one B-ranked
helper. This made a small but domain-important metadata contract harder to review and keep
consistent with other transaction metadata enrichers.

## Action

Added focused helpers for SELL transaction eligibility, SELL linkage ID resolution, SELL policy ID
resolution, cost-basis policy selection, and SELL metadata update assembly.

## Result

`enrich_sell_transaction_metadata` improved from `B (7)` to `A (2)`. All SELL linkage functions
now report A-ranked cyclomatic complexity, and `sell_linkage.py` remains A-ranked maintainability
at `A (67.86)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio_common\test_sell_linkage.py tests\unit\libs\portfolio_common\test_sell_validation.py tests\unit\libs\portfolio_common\test_transaction_control_code_models.py -q`
  => 16 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\transaction_domain\sell_linkage.py tests\unit\libs\portfolio_common\test_sell_linkage.py tests\unit\libs\portfolio_common\test_sell_validation.py tests\unit\libs\portfolio_common\test_transaction_control_code_models.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\transaction_domain\sell_linkage.py tests\unit\libs\portfolio_common\test_sell_linkage.py tests\unit\libs\portfolio_common\test_sell_validation.py tests\unit\libs\portfolio_common\test_transaction_control_code_models.py`
  => 4 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\transaction_domain\sell_linkage.py -s`
  => `enrich_sell_transaction_metadata` `A (2)`; all SELL linkage functions A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\transaction_domain\sell_linkage.py -s`
  => `sell_linkage.py` `A (67.86)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\transaction_domain\sell_linkage.py`
  => 59 SLOC / 32 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal transaction-domain helper refactor that
preserves SELL metadata enrichment behavior and operator-facing documentation truth.
