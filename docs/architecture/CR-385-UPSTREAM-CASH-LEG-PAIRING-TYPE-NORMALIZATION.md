# CR-385: Upstream Cash-Leg Pairing Type Normalization

Date: 2026-05-28

## Scope

Shared upstream-provided cash-leg pairing validation in `portfolio_common.transaction_domain`.

## Finding

Upstream cash-leg pairing validation uppercased the cash-leg transaction type without trimming
source values. A padded lower-case value such as ` adjustment ` could reject an otherwise valid
upstream-provided settlement pair even when the portfolio, external cash transaction id, amount,
economic event, and linked transaction group matched.

This mattered because upstream-provided cash legs are part of settlement-sensitive booking flows
where pairing errors can block valid bank-owned cash evidence.

## Change

Added local control-code normalization before validating that the cash leg is an `ADJUSTMENT`.
Updated the direct pairing test to prove padded lower-case adjustment cash legs are accepted when
the rest of the pair is valid.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio_common/test_dual_leg_pairing.py -q`
2. `python -m pytest tests/unit/libs/portfolio_common -q`
3. `python -m ruff check src/libs/portfolio-common/portfolio_common/transaction_domain/dual_leg_pairing.py tests/unit/libs/portfolio_common/test_dual_leg_pairing.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a shared
transaction-domain booking reliability slice for upstream cash-leg pairing.
