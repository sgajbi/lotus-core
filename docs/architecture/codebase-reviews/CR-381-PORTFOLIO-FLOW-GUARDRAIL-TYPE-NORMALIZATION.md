# CR-381: Portfolio Flow Guardrail Type Normalization

Date: 2026-05-28

## Scope

Shared portfolio-flow cash-entry-mode guardrails in `portfolio_common.transaction_domain`.

## Finding

The shared portfolio-flow guardrail uppercased transaction types without trimming source values.
Padded lower-case values such as ` fee `, ` deposit `, or ` transfer_out ` could miss the governed
portfolio-flow transaction-type set and allow `AUTO_GENERATE` cash entry mode for transaction
families that require bank-owned cash movements rather than synthetic cash generation.

This mattered because the helper is used by both cashflow and cost calculator consumers before
booking portfolio-level flows.

## Change

Trimmed and uppercased transaction types before checking the portfolio-flow no-auto-generate set.
Added direct guardrail tests proving padded lower-case portfolio-flow types still reject
`AUTO_GENERATE` cash entry mode while unrelated transaction types remain outside the blocked set.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio_common/test_portfolio_flow_guardrails.py -q`
2. `python -m pytest tests/unit/libs/portfolio_common -q`
3. `python -m ruff check src/libs/portfolio-common/portfolio_common/transaction_domain/portfolio_flow_guardrails.py tests/unit/libs/portfolio_common/test_portfolio_flow_guardrails.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a shared
transaction-domain control hardening slice for portfolio-level flow booking safety.
