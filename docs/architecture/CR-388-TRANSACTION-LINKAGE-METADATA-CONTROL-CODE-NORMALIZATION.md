# CR-388: Transaction Linkage Metadata Control-Code Normalization

Date: 2026-05-28

## Scope

BUY, SELL, DIVIDEND, and INTEREST linkage metadata enrichment in
`portfolio_common.transaction_domain`.

## Finding

Transaction linkage helpers uppercased transaction types without trimming source values. Padded
lower-case values such as ` buy `, ` sell `, ` dividend `, or ` interest ` could skip deterministic
economic-event, linked-transaction-group, calculation-policy, and cash-entry-mode enrichment for
otherwise valid transaction events.

This mattered because these helpers attach the metadata required for downstream booking,
calculation, auditability, and lineage controls.

## Change

Reused the shared transaction-domain control-code normalizer across BUY, SELL, DIVIDEND, and
INTEREST linkage helpers. Updated direct linkage tests to prove padded lower-case transaction
family codes still receive deterministic default metadata while upstream-provided values remain
preserved by existing tests.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio_common/test_buy_linkage.py tests/unit/libs/portfolio_common/test_sell_linkage.py tests/unit/libs/portfolio_common/test_dividend_linkage.py tests/unit/libs/portfolio_common/test_interest_linkage.py -q`
2. `python -m pytest tests/unit/libs/portfolio_common -q`
3. `python -m ruff check src/libs/portfolio-common/portfolio_common/transaction_domain/buy_linkage.py src/libs/portfolio-common/portfolio_common/transaction_domain/sell_linkage.py src/libs/portfolio-common/portfolio_common/transaction_domain/dividend_linkage.py src/libs/portfolio-common/portfolio_common/transaction_domain/interest_linkage.py tests/unit/libs/portfolio_common/test_buy_linkage.py tests/unit/libs/portfolio_common/test_sell_linkage.py tests/unit/libs/portfolio_common/test_dividend_linkage.py tests/unit/libs/portfolio_common/test_interest_linkage.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a shared
transaction-domain lineage and auditability reliability slice for deterministic transaction
metadata enrichment.
