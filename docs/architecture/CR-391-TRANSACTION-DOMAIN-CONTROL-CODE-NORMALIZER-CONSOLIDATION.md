# CR-391: Transaction-Domain Control-Code Normalizer Consolidation

Date: 2026-05-28

## Scope

Shared transaction-domain control-code normalization in `portfolio_common.transaction_domain`.

## Finding

Several transaction-domain helpers still carried local `strip().upper()` normalizer functions or
inline normalization expressions after the shared helper was introduced. The behavior was already
consistent today, but duplicate normalizers create drift risk in validation, cash-leg generation,
FX processing, FX synthetic instrument creation, pairing, and effective processing-type routing.

## Change

Reused `normalize_transaction_control_code(...)` across the remaining transaction-domain helpers:
cash-entry mode normalization, adjustment cash-leg generation, upstream cash-leg pairing,
effective processing-type resolution, FX baseline processing, FX contract instrument generation,
and portfolio-flow cash-entry guardrails. Removed duplicate local normalizer implementations so
the package has one canonical control-code normalization point.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio_common/test_adjustment_cash_leg.py tests/unit/libs/portfolio_common/test_dual_leg_pairing.py tests/unit/libs/portfolio_common/test_fx_contract_instrument.py tests/unit/libs/portfolio_common/test_effective_processing_type.py tests/unit/libs/portfolio_common/test_cash_entry_mode.py tests/unit/libs/portfolio_common/test_fx_baseline_processing.py tests/unit/libs/portfolio_common/test_portfolio_flow_guardrails.py -q`
2. `python -m pytest tests/unit/libs/portfolio_common -q`
3. `python -m ruff check src/libs/portfolio-common/portfolio_common/transaction_domain/adjustment_cash_leg.py src/libs/portfolio-common/portfolio_common/transaction_domain/dual_leg_pairing.py src/libs/portfolio-common/portfolio_common/transaction_domain/fx_contract_instrument.py src/libs/portfolio-common/portfolio_common/transaction_domain/effective_processing_type.py src/libs/portfolio-common/portfolio_common/transaction_domain/cash_entry_mode.py src/libs/portfolio-common/portfolio_common/transaction_domain/fx_baseline_processing.py src/libs/portfolio-common/portfolio_common/transaction_domain/portfolio_flow_guardrails.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a shared
transaction-domain maintainability and calculation-control reliability slice.
