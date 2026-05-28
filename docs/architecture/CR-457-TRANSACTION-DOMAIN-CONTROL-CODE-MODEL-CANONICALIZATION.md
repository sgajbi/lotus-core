# CR-457: Transaction Domain Control-Code Model Canonicalization

Date: 2026-05-28

## Scope

Shared `portfolio_common.transaction_domain` canonical transaction models for BUY, SELL, DIVIDEND,
INTEREST, and FX components.

## Finding

The transaction-domain validators, linkage builders, adjustment cash-leg generation, and FX
baseline processing already normalized many control-code fields defensively. The canonical model
boundary still preserved raw caller casing and whitespace for fields such as `transaction_type`,
`cash_entry_mode`, `interest_direction`, `component_type`, `fx_rate_quote_convention`,
`fx_cash_leg_role`, settlement status, spot exposure mode, and realized FX P&L mode.

That left unnecessary repeated normalization on calculation-branching paths and allowed
non-canonical control-code values to travel through model instances before later validation or
linkage logic interpreted them.

## Change

Added model-boundary control-code canonicalization while preserving the existing semantic
validators as the source of business validity:

1. BUY, SELL, DIVIDEND, and INTEREST models canonicalize `transaction_type`,
2. DIVIDEND and INTEREST models canonicalize optional `cash_entry_mode` without defaulting omitted
   values,
3. INTEREST models canonicalize optional `interest_direction`,
4. FX models canonicalize required `transaction_type`, `component_type`, and
   `fx_rate_quote_convention`,
5. FX models canonicalize optional `fx_cash_leg_role`, `settlement_status`,
   `spot_exposure_model`, and `fx_realized_pnl_mode` without defaulting omitted values,
6. added focused shared-library tests proving padded lower-case control-code input is normalized at
   model construction time and implicit optional modes remain `None` until downstream processing
   applies documented defaults.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio_common/test_transaction_control_code_models.py -q`
2. `python -m pytest tests/unit/libs/portfolio_common/test_buy_validation.py tests/unit/libs/portfolio_common/test_sell_validation.py tests/unit/libs/portfolio_common/test_dividend_validation.py tests/unit/libs/portfolio_common/test_interest_validation.py tests/unit/libs/portfolio_common/test_fx_validation.py -q`
3. `python -m pytest tests/unit/libs/portfolio_common/test_buy_linkage.py tests/unit/libs/portfolio_common/test_sell_linkage.py tests/unit/libs/portfolio_common/test_dividend_linkage.py tests/unit/libs/portfolio_common/test_interest_linkage.py tests/unit/libs/portfolio_common/test_fx_linkage.py tests/unit/libs/portfolio_common/test_adjustment_cash_leg.py tests/unit/libs/portfolio_common/test_fx_baseline_processing.py -q`
4. `python -m ruff check src/libs/portfolio-common/portfolio_common/transaction_domain/control_code_normalization.py src/libs/portfolio-common/portfolio_common/transaction_domain/buy_models.py src/libs/portfolio-common/portfolio_common/transaction_domain/sell_models.py src/libs/portfolio-common/portfolio_common/transaction_domain/dividend_models.py src/libs/portfolio-common/portfolio_common/transaction_domain/interest_models.py src/libs/portfolio-common/portfolio_common/transaction_domain/fx_models.py tests/unit/libs/portfolio_common/test_transaction_control_code_models.py`
5. `python -m pytest tests/unit/libs/portfolio_common -q`
6. `git diff --check`

Results:

1. Focused transaction control-code model pytest: `8 passed`
2. Transaction validation pack: `45 passed`
3. Transaction linkage and baseline processing pack: `21 passed`
4. Touched-surface ruff: passed
5. Portfolio-common unit pack: `136 passed`
6. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. This
slice keeps the model boundary canonical while leaving unknown or unsupported control-code
decisions with the existing transaction-domain validators, so callers still receive the governed
reason-code behavior already used by downstream certification tests.
