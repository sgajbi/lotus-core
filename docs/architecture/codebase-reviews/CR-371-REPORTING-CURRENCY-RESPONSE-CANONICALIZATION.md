# CR-371: Reporting Currency Response Canonicalization

Date: 2026-05-28

## Scope

Query-service reporting and cash-balance response currency fields used by AUM, portfolio summary,
asset allocation, and cash-balance products.

## Finding

Reporting and cash-balance conversion helpers already normalized currency codes before FX identity
checks, cache keys, and repository calls. Some response fields still echoed raw portfolio,
requested reporting, or account currency values. Padded lower-case inputs such as ` usd ` and
` sgd ` could therefore produce canonical calculations while returning non-canonical response
metadata.

That mismatch weakens downstream reconciliation and supportability because product consumers may
compare response currency fields against the canonical FX basis used to calculate totals.

## Change

Reused the shared query-service currency normalizer for:

1. reporting-currency resolution for reporting service products,
2. AUM portfolio summary `portfolio_currency` fields,
3. portfolio summary `portfolio_currency` and `reporting_currency`,
4. cash-balance response `portfolio_currency` and `reporting_currency`,
5. cash account `account_currency` fields,
6. cash-balance service default reporting-currency resolution.

The calculation path still uses the existing normalized FX cache and repository calls. This slice
aligns response metadata with that canonical calculation basis.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_reporting_service.py tests/unit/services/query_service/services/test_cash_balance_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/reporting_service.py src/services/query_service/app/services/cash_balance_service.py tests/unit/services/query_service/services/test_reporting_service.py tests/unit/services/query_service/services/test_cash_balance_service.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is response-metadata
reliability hardening for existing reporting and cash-balance source-data products.
