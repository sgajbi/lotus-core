# CR-387: Canonical Transaction Validation Control-Code Normalization

Date: 2026-05-28

## Scope

BUY, SELL, DIVIDEND, and INTEREST canonical transaction validation in
`portfolio_common.transaction_domain`.

## Finding

Canonical transaction validators uppercased transaction types, and INTEREST direction, without
trimming source values. Padded lower-case values such as ` buy `, ` sell `, ` dividend `,
` interest `, or ` expense ` could raise invalid transaction-type or interest-direction findings
for otherwise valid canonical transaction events.

This mattered because these validators are shared booking controls used before downstream
calculation and persistence paths can rely on transaction-family semantics.

## Change

Added a shared transaction-domain control-code normalizer and reused it across BUY, SELL, DIVIDEND,
and INTEREST validation. Updated direct validation tests to prove padded lower-case transaction
types and INTEREST expense direction are accepted when the rest of the canonical event is valid.
Removed an existing duplicate dividend auto-generate cash-account test definition that ruff exposed
while validating the touched test file.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio_common/test_buy_validation.py tests/unit/libs/portfolio_common/test_sell_validation.py tests/unit/libs/portfolio_common/test_dividend_validation.py tests/unit/libs/portfolio_common/test_interest_validation.py -q`
2. `python -m pytest tests/unit/libs/portfolio_common -q`
3. `python -m ruff check src/libs/portfolio-common/portfolio_common/transaction_domain/control_code_normalization.py src/libs/portfolio-common/portfolio_common/transaction_domain/buy_validation.py src/libs/portfolio-common/portfolio_common/transaction_domain/sell_validation.py src/libs/portfolio-common/portfolio_common/transaction_domain/dividend_validation.py src/libs/portfolio-common/portfolio_common/transaction_domain/interest_validation.py tests/unit/libs/portfolio_common/test_buy_validation.py tests/unit/libs/portfolio_common/test_sell_validation.py tests/unit/libs/portfolio_common/test_dividend_validation.py tests/unit/libs/portfolio_common/test_interest_validation.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a shared
transaction-domain validation reliability slice for deterministic canonical transaction-family
classification.
