# CR-456: Transaction Domain Currency Model Canonicalization

Date: 2026-05-28

## Scope

Shared `portfolio_common.transaction_domain` canonical transaction models for BUY, SELL, DIVIDEND,
INTEREST, and FX components.

## Finding

The transaction-domain Pydantic models are used before validation, linkage, cash-leg generation,
and calculation-policy logic. Their currency fields accepted raw caller strings, so direct model
construction with padded or lower-case values could carry non-canonical trade, book, FX pair,
bought, or sold currencies into downstream validators and calculators.

## Change

Reused the shared portfolio-common currency-code normalizer at the canonical transaction model
boundary:

1. BUY, SELL, DIVIDEND, and INTEREST models canonicalize `trade_currency` and `currency`,
2. FX models canonicalize `trade_currency`, `currency`, `pair_base_currency`,
   `pair_quote_currency`, `buy_currency`, and `sell_currency`,
3. added focused shared-library tests proving padded lower-case currency input is normalized at
   model construction time before downstream validation/linkage logic.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio_common/test_transaction_currency_models.py -q`
2. `python -m pytest tests/unit/libs/portfolio_common/test_buy_validation.py tests/unit/libs/portfolio_common/test_sell_validation.py tests/unit/libs/portfolio_common/test_dividend_validation.py tests/unit/libs/portfolio_common/test_interest_validation.py tests/unit/libs/portfolio_common/test_fx_validation.py -q`
3. `python -m ruff check src/libs/portfolio-common/portfolio_common/transaction_domain/buy_models.py src/libs/portfolio-common/portfolio_common/transaction_domain/sell_models.py src/libs/portfolio-common/portfolio_common/transaction_domain/dividend_models.py src/libs/portfolio-common/portfolio_common/transaction_domain/interest_models.py src/libs/portfolio-common/portfolio_common/transaction_domain/fx_models.py tests/unit/libs/portfolio_common/test_transaction_currency_models.py`
4. `python -m pytest tests/unit/libs/portfolio_common -q`
5. `git diff --check`

Results:

1. Focused transaction currency model pytest: `5 passed`
2. Transaction validation pack: `45 passed`
3. Touched-surface ruff: passed
4. Portfolio-common unit pack: `128 passed`
5. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. The
shared transaction-domain model boundary is intentionally stricter: valid transaction currencies
are canonicalized and invalid non-three-letter values fail before validation and calculation
logic consumes the model.
