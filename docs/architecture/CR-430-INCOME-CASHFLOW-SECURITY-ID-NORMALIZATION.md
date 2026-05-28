# CR-430: Income Cashflow Security-ID Normalization

Date: 2026-05-28

## Scope

Query-service cashflow repository income-cashflow lookup for a single position.

## Finding

`get_income_cashflows_for_position(...)` filtered cashflows and joined position-state rows by raw
persisted `security_id` values. Whitespace drift between a request, booked cashflow row, and
position-state row could exclude valid dividend, coupon, or other income cashflows for a holding.

That is a calculation correctness risk because position income cashflows feed return, income, and
cash movement evidence used by private banking analytics.

## Change

Reused the shared query-service security identifier normalizer at the income-cashflow query
boundary. The repository now trims the requested security identifier, fails closed for blank
identifiers without hitting the database, compares cashflow and position-state identifiers through
trimmed SQL expressions, and filters the cashflow rows by the canonical requested identifier.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_query_cashflow_repository.py -q`
2. `python -m ruff check src/services/query_service/app/repositories/cashflow_repository.py tests/unit/services/query_service/repositories/test_query_cashflow_repository.py`
3. `python -m pytest tests/unit/services/query_service/repositories -q`
4. `git diff --check`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is a
calculation-input hardening slice that protects position-level income evidence from harmless source
identifier padding.
