# CR-436: Cash Account Fallback Security-ID Normalization

Date: 2026-05-28

## Scope

Query-service reporting repository cash-account fallback resolution used by cash balance and
portfolio summary views.

## Finding

`ReportingRepository.get_latest_cash_account_ids(...)` filtered and partitioned fallback
settlement transactions by raw `settlement_cash_instrument_id`. Whitespace drift between cash
snapshot identifiers and transaction settlement cash instrument identifiers could prevent cash
balances from resolving to the right cash account when account master data was incomplete.

That is a liquidity and reporting correctness risk because cash account mapping affects cash
balance detail, cash totals, and portfolio summary evidence.

## Change

Reused the shared query-service security identifier normalizer at the cash-account fallback query
boundary. The repository now trims and skips blank requested cash security identifiers, filters and
partitions settlement transactions by `trim(transactions.settlement_cash_instrument_id)`, and
returns canonical cash security identifiers as map keys.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_reporting_repository.py -q`
2. `python -m ruff check src/services/query_service/app/repositories/reporting_repository.py tests/unit/services/query_service/repositories/test_reporting_repository.py`
3. `python -m pytest tests/unit/services/query_service/repositories -q`
4. `python -m pytest tests/unit/services/query_service/services -q`
5. `git diff --check`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is a liquidity
reporting hardening slice that prevents source identifier padding from breaking cash-account
fallback resolution.
