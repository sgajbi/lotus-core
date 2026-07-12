# CR-983: FX Contract Instrument Helper Boundary

Date: 2026-06-05

## Scope

Split FX contract instrument event construction into focused domain helper boundaries without
changing component eligibility, missing-contract-ID behavior, generated instrument security ID,
synthetic ISIN, display name, currency selection, maturity/trade dates, pair currency fields,
amount fields, contract rate, or returned `InstrumentEvent` shape.

## Finding

`build_fx_contract_instrument_event` mixed component eligibility, FX contract ID resolution,
currency normalization, maturity/trade date extraction, pair label assembly, display-name
assembly, and `InstrumentEvent` construction in one C-ranked function. This made FX contract
instrument derivation harder to review as a transaction-domain support path.

## Action

Added focused helpers for FX contract ID resolution, contract currency normalization, pair label
resolution, display-name construction, and final `InstrumentEvent` assembly.

## Result

`build_fx_contract_instrument_event` improved from `C (13)` to `A (5)`. All FX contract
instrument functions now report A-ranked cyclomatic complexity, and `fx_contract_instrument.py`
remains A-ranked maintainability at `A (51.08)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio_common\test_fx_contract_instrument.py tests\unit\libs\portfolio_common\test_fx_baseline_processing.py tests\unit\libs\portfolio_common\test_fx_validation.py tests\unit\libs\portfolio_common\test_fx_linkage.py -q`
  => 24 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\transaction_domain\fx_contract_instrument.py tests\unit\libs\portfolio_common\test_fx_contract_instrument.py tests\unit\libs\portfolio_common\test_fx_baseline_processing.py tests\unit\libs\portfolio_common\test_fx_validation.py tests\unit\libs\portfolio_common\test_fx_linkage.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\transaction_domain\fx_contract_instrument.py tests\unit\libs\portfolio_common\test_fx_contract_instrument.py tests\unit\libs\portfolio_common\test_fx_baseline_processing.py tests\unit\libs\portfolio_common\test_fx_validation.py tests\unit\libs\portfolio_common\test_fx_linkage.py`
  => 5 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\transaction_domain\fx_contract_instrument.py -s`
  => `build_fx_contract_instrument_event` `A (5)`; all FX contract instrument functions A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\transaction_domain\fx_contract_instrument.py -s`
  => `fx_contract_instrument.py` `A (51.08)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\transaction_domain\fx_contract_instrument.py`
  => 73 SLOC / 36 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal transaction-domain helper refactor that
preserves FX contract instrument derivation behavior and operator-facing documentation truth.
