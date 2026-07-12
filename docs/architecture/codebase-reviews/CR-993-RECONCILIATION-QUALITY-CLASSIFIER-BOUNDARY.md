# CR-993: Reconciliation Quality Classifier Boundary

Date: 2026-06-05

## Scope

Split reconciliation run and data-quality coverage classification into validation helpers, focused
status decision helpers, and small policy predicates without changing status precedence,
non-negative validation, finding classification, break sorting, or market/reference coverage
behavior.

## Finding

`classify_reconciliation_status` mixed run-count validation, missing-run handling, status
normalization, blocking/error precedence, stale precedence, warning precedence, complete/running
status classification, and unknown fallback in one B-ranked helper.
`classify_data_quality_coverage` similarly mixed count validation, blocking issues, unknown
coverage, unreconciled coverage, stale coverage, partial coverage, and complete coverage in one
B-ranked helper.

## Action

Added focused validation helpers, status-decision helpers, a run-status classification map, and
small blocking/partial predicates. The public classifiers now validate input and delegate to
explicit precedence helpers.

## Result

`classify_reconciliation_status` improved from `B (9)` to `A (2)`, and
`classify_data_quality_coverage` improved from `B (7)` to `A (1)`. All functions/classes in
`reconciliation_quality.py` now report A-ranked cyclomatic complexity, and the module remains
A-ranked maintainability at `A (33.27)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_reconciliation_quality.py tests\unit\libs\portfolio-common\test_market_reference_quality.py -q`
  => 48 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\reconciliation_quality.py tests\unit\libs\portfolio-common\test_reconciliation_quality.py tests\unit\libs\portfolio-common\test_market_reference_quality.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\reconciliation_quality.py tests\unit\libs\portfolio-common\test_reconciliation_quality.py tests\unit\libs\portfolio-common\test_market_reference_quality.py`
  => 3 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\reconciliation_quality.py -s`
  => `classify_reconciliation_status` `A (2)`, `classify_data_quality_coverage` `A (1)`, and all functions/classes A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\reconciliation_quality.py -s`
  => `reconciliation_quality.py` `A (33.27)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\reconciliation_quality.py`
  => 172 SLOC / 128 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared reconciliation/data-quality helper
refactor that preserves API and operator-facing quality semantics.
