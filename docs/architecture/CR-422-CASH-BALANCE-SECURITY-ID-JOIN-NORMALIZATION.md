# CR-422: Cash Balance Security-ID Join Normalization

Date: 2026-05-28

## Scope

Query-service cash-balance assembly for `HoldingsAsOf` cash account balances.

## Finding

Cash balance response construction joined cash-account master rows, latest snapshot rows, and
fallback cash-account mappings by raw `security_id` values. A cash-account master identifier with
surrounding whitespace could fail to join to the actual cash snapshot row, causing the account to
be emitted as a zero-balance master account even though the portfolio had a real cash balance.

That failure mode can understate portfolio cash, liquidity, and reporting totals while the source
snapshot data is present.

## Change

Added security identifier normalization for cash-balance assembly. The resolver now trims cash
snapshot identifiers before fallback lookup, trims master and snapshot join keys, trims fallback
mapping keys, and emits canonical trimmed cash security identifiers in cash-balance records.

Currency normalization remains handled by the existing query-service currency-code normalizer.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_cash_balance_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/cash_balance_service.py tests/unit/services/query_service/services/test_cash_balance_service.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is a
service-boundary correctness slice that keeps cash-account balances and totals from silently
understating portfolio cash because of whitespace drift in source identifiers.
