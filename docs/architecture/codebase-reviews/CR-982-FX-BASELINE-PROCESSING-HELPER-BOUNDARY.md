# CR-982: FX Baseline Processing Helper Boundary

Date: 2026-06-05

## Scope

Split FX baseline processed-event construction into focused domain helper boundaries without
changing realized P&L mode normalization, decimal defaulting behavior, zero-realized-P&L behavior,
upstream-provided realized P&L aggregation, event copy semantics, or strict FX validation behavior.

## Finding

`build_fx_processed_event` mixed realized P&L mode normalization, base cost/default field
assembly, NONE-mode zeroing, upstream-provided capital/FX P&L extraction, and total P&L fallback
calculation in one C-ranked function. This made FX baseline processing harder to review as an
interim transaction-domain policy.

## Action

Added focused helpers for decimal defaulting, base FX processing update assembly, realized P&L
mode dispatch, zero realized P&L update assembly, upstream-provided realized P&L update assembly,
and total P&L fallback resolution.

## Result

`build_fx_processed_event` improved from `C (14)` to `A (2)`. All FX baseline processing
functions now report A-ranked cyclomatic complexity, and `fx_baseline_processing.py` remains
A-ranked maintainability at `A (65.60)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio_common\test_fx_baseline_processing.py tests\unit\libs\portfolio_common\test_fx_validation.py tests\unit\libs\portfolio_common\test_fx_linkage.py tests\unit\libs\portfolio_common\test_fx_contract_instrument.py -q`
  => 24 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\transaction_domain\fx_baseline_processing.py tests\unit\libs\portfolio_common\test_fx_baseline_processing.py tests\unit\libs\portfolio_common\test_fx_validation.py tests\unit\libs\portfolio_common\test_fx_linkage.py tests\unit\libs\portfolio_common\test_fx_contract_instrument.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\transaction_domain\fx_baseline_processing.py tests\unit\libs\portfolio_common\test_fx_baseline_processing.py tests\unit\libs\portfolio_common\test_fx_validation.py tests\unit\libs\portfolio_common\test_fx_linkage.py tests\unit\libs\portfolio_common\test_fx_contract_instrument.py`
  => 5 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\transaction_domain\fx_baseline_processing.py -s`
  => `build_fx_processed_event` `A (2)`; all FX baseline processing functions A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\transaction_domain\fx_baseline_processing.py -s`
  => `fx_baseline_processing.py` `A (65.60)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\transaction_domain\fx_baseline_processing.py`
  => 74 SLOC / 39 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal transaction-domain helper refactor that
preserves FX baseline processing behavior and operator-facing documentation truth.
