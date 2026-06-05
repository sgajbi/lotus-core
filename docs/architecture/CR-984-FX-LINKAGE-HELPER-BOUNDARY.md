# CR-984: FX Linkage Helper Boundary

Date: 2026-06-05

## Scope

Split FX linkage enrichment into focused domain helper boundaries without changing business
transaction filtering, generated economic event IDs, linked transaction group IDs, swap group IDs,
FX contract IDs, contract instrument routing, lifecycle transaction IDs, cash-leg role inference,
policy defaults, component IDs, spot exposure model normalization, or realized P&L mode
normalization.

## Finding

`enrich_fx_transaction_metadata` mixed FX transaction classification, linkage defaults, swap group
defaults, contract ID derivation, instrument routing, lifecycle IDs, policy defaults, cash-leg role
inference, and processing mode normalization in one B-ranked function. Two supporting helpers also
remained B-ranked for FX contract ID and lifecycle transaction resolution.

## Action

Added focused helpers for contract ID decision predicates, open/close lifecycle transaction IDs,
FX metadata update assembly, core linkage update fields, contract linkage update fields,
instrument lifecycle update fields, and FX processing mode update fields.

## Result

`enrich_fx_transaction_metadata` improved from `B (7)` to `A (2)`,
`_resolve_fx_contract_id` improved from `B (6)` to `A (4)`, and
`_resolve_contract_lifecycle_transaction_ids` improved from `B (7)` to `A (3)`. All FX linkage
functions now report A-ranked cyclomatic complexity, and `fx_linkage.py` remains A-ranked
maintainability at `A (42.62)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio_common\test_fx_linkage.py tests\unit\libs\portfolio_common\test_fx_validation.py tests\unit\libs\portfolio_common\test_fx_contract_instrument.py tests\unit\libs\portfolio_common\test_fx_baseline_processing.py -q`
  => 24 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\transaction_domain\fx_linkage.py tests\unit\libs\portfolio_common\test_fx_linkage.py tests\unit\libs\portfolio_common\test_fx_validation.py tests\unit\libs\portfolio_common\test_fx_contract_instrument.py tests\unit\libs\portfolio_common\test_fx_baseline_processing.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\transaction_domain\fx_linkage.py tests\unit\libs\portfolio_common\test_fx_linkage.py tests\unit\libs\portfolio_common\test_fx_validation.py tests\unit\libs\portfolio_common\test_fx_contract_instrument.py tests\unit\libs\portfolio_common\test_fx_baseline_processing.py`
  => 5 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\transaction_domain\fx_linkage.py -s`
  => all FX linkage functions A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\transaction_domain\fx_linkage.py -s`
  => `fx_linkage.py` `A (42.62)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\transaction_domain\fx_linkage.py`
  => 228 SLOC / 90 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal transaction-domain helper refactor that
preserves FX linkage enrichment behavior and operator-facing documentation truth.
