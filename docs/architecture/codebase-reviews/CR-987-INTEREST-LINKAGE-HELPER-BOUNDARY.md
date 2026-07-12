# CR-987: Interest Linkage Helper Boundary

Date: 2026-06-05

## Scope

Split INTEREST transaction metadata enrichment into focused domain helper boundaries without
changing transaction-type eligibility, generated economic event IDs, linked transaction group IDs,
default policy IDs, default policy versions, cash-entry mode normalization, upstream value
preservation, or returned event-copy behavior.

## Finding

`enrich_interest_transaction_metadata` mixed INTEREST eligibility, deterministic linkage ID
defaults, policy-default resolution, cash-entry mode normalization, and update assembly in one
B-ranked helper. This made the metadata enrichment contract harder to review and align with other
transaction metadata helpers.

## Action

Added focused helpers for INTEREST transaction eligibility, INTEREST linkage ID resolution,
INTEREST policy ID resolution, and INTEREST metadata update assembly.

## Result

`enrich_interest_transaction_metadata` improved from `B (6)` to `A (2)`. All INTEREST linkage
functions now report A-ranked cyclomatic complexity, and `interest_linkage.py` remains A-ranked
maintainability at `A (71.82)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio_common\test_interest_linkage.py tests\unit\libs\portfolio_common\test_interest_validation.py tests\unit\libs\portfolio_common\test_transaction_control_code_models.py -q`
  => 24 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\transaction_domain\interest_linkage.py tests\unit\libs\portfolio_common\test_interest_linkage.py tests\unit\libs\portfolio_common\test_interest_validation.py tests\unit\libs\portfolio_common\test_transaction_control_code_models.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\transaction_domain\interest_linkage.py tests\unit\libs\portfolio_common\test_interest_linkage.py tests\unit\libs\portfolio_common\test_interest_validation.py tests\unit\libs\portfolio_common\test_transaction_control_code_models.py`
  => 4 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\transaction_domain\interest_linkage.py -s`
  => `enrich_interest_transaction_metadata` `A (2)`; all INTEREST linkage functions A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\transaction_domain\interest_linkage.py -s`
  => `interest_linkage.py` `A (71.82)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\transaction_domain\interest_linkage.py`
  => 50 SLOC / 26 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal transaction-domain helper refactor that
preserves INTEREST metadata enrichment behavior and operator-facing documentation truth.
