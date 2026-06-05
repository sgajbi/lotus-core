# CR-992: Market Reference Point Classifier Boundary

Date: 2026-06-05

## Scope

Split market/reference point quality classification into explicit status-precedence maps and a
focused status decision helper without changing observed-at resolution, timezone validation,
blocking/stale precedence, missing-observation behavior, coverage classification, or quality-status
summary behavior.

## Finding

`classify_market_reference_point` mixed source observation resolution, quality-status
normalization, blocking/stale precedence, missing-observation handling, accepted/partial
classification, and unknown fallback in one B-ranked helper. This made RFC-0083 market/reference
quality semantics harder to review and extend.

## Action

Added explicit pre-observation and observed-status classification maps and extracted the point
status decision into a focused helper. The public classifier now resolves observation time,
normalizes quality status, and delegates the deterministic status classification.

## Result

`classify_market_reference_point` improved from `B (8)` to `A (1)`. All functions/classes in
`market_reference_quality.py` now report A-ranked cyclomatic complexity, and the module remains
A-ranked maintainability at `A (36.36)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_market_reference_quality.py -q`
  => 21 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\market_reference_quality.py tests\unit\libs\portfolio-common\test_market_reference_quality.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\market_reference_quality.py tests\unit\libs\portfolio-common\test_market_reference_quality.py`
  => 2 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\market_reference_quality.py -s`
  => `classify_market_reference_point` `A (1)` and all functions/classes A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\market_reference_quality.py -s`
  => `market_reference_quality.py` `A (36.36)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\market_reference_quality.py`
  => 122 SLOC / 95 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal market/reference quality helper refactor
that preserves API and operator-facing quality semantics.
