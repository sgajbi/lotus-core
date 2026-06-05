# CR-991: Analytics Cashflow Semantics Classifier Boundary

Date: 2026-06-05

## Scope

Split analytics cashflow semantic classification into static classification mapping and focused
transfer-flow policy without changing cashflow type, flow scope, amount normalization, timing
normalization, or query-service cashflow observation behavior.

## Finding

`classify_analytics_cash_flow` mixed external-flow, internal-trade-flow, transfer, income, fee,
and unknown classification policy in one B-ranked helper. This made analytics cashflow semantics
harder to review as the canonical cashflow vocabulary grew.

## Action

Added a typed static cashflow semantics map for fixed classifications and extracted the
position-versus-portfolio transfer decision into a focused helper. The public classifier now
normalizes the classification, handles transfer policy, and otherwise performs a deterministic
lookup with the existing unknown fallback.

## Result

`classify_analytics_cash_flow` improved from `B (10)` to `A (3)`. All functions in
`analytics_cashflow_semantics.py` now report A-ranked cyclomatic complexity, and the module remains
A-ranked maintainability at `A (74.86)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_analytics_cashflow_semantics.py tests\unit\services\query_service\services\test_analytics_cash_flows.py -q`
  => 30 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\analytics_cashflow_semantics.py tests\unit\libs\portfolio-common\test_analytics_cashflow_semantics.py tests\unit\services\query_service\services\test_analytics_cash_flows.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\analytics_cashflow_semantics.py tests\unit\libs\portfolio-common\test_analytics_cashflow_semantics.py tests\unit\services\query_service\services\test_analytics_cash_flows.py`
  => 3 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\analytics_cashflow_semantics.py -s`
  => `classify_analytics_cash_flow` `A (3)` and all functions A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\analytics_cashflow_semantics.py -s`
  => `analytics_cashflow_semantics.py` `A (74.86)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\analytics_cashflow_semantics.py`
  => 51 SLOC / 25 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal analytics semantics helper refactor that
preserves API response semantics and operator-facing documentation truth.
