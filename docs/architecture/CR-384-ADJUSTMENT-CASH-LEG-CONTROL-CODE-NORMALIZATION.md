# CR-384: Adjustment Cash-Leg Control-Code Normalization

Date: 2026-05-28

## Scope

Shared adjustment cash-leg generation in `portfolio_common.transaction_domain`.

## Finding

Adjustment cash-leg generation uppercased transaction types and interest direction without trimming
source values. Padded lower-case values such as ` dividend `, ` interest `, or ` expense ` could:

1. suppress otherwise valid auto-generated settlement cash legs,
2. reject eligible product transactions as non-eligible,
3. classify an interest expense as an inflow instead of an outflow.

This mattered because the helper creates deterministic linked cash legs for settlement-sensitive
booking flows.

## Change

Added local control-code normalization for transaction type and interest direction comparisons.
Updated direct tests to prove padded lower-case dividend transactions still create the expected
cash leg and padded lower-case interest expense direction produces an outflow cash leg with the
correct adjustment reason.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio_common/test_adjustment_cash_leg.py -q`
2. `python -m pytest tests/unit/libs/portfolio_common -q`
3. `python -m ruff check src/libs/portfolio-common/portfolio_common/transaction_domain/adjustment_cash_leg.py tests/unit/libs/portfolio_common/test_adjustment_cash_leg.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a shared
transaction-domain booking reliability slice for deterministic settlement cash-leg generation.
