# CR-375: Cash Balance Asset-Class Normalization

Date: 2026-05-28

## Scope

Query-service `HoldingsAsOf` cash-balance account detection and cash-balance totals.

## Finding

`CashBalanceResolver.is_cash_row` uppercased instrument `asset_class` values without trimming source
whitespace. Padded lower-case values such as ` cash ` could cause genuine cash account rows to be
excluded from the cash-balance product, which would:

1. understate cash account count,
2. understate portfolio-currency and reporting-currency cash totals,
3. mark cash-balance data quality as `UNKNOWN` despite usable cash evidence,
4. drop latest snapshot evidence timestamps for valid cash rows.

This mattered because cash-balance output feeds private-bank liquidity, reporting, and advisor
operating workflows.

## Change

Added cash-balance control-code normalization for asset-class classification before cash row
detection. Updated the primary cash-balance service test to prove padded `cash` source values still
produce the correct account count, cash totals, canonical currencies, and FX conversion behavior.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_cash_balance_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/cash_balance_service.py tests/unit/services/query_service/services/test_cash_balance_service.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a calculation-path
reliability hardening slice for the existing cash-balance source-data product.
