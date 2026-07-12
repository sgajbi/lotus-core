# CR-443: Missing FX Currency-Code Normalization

Date: 2026-05-28

## Scope

Query-service operations repository missing historical FX dependency evidence.

## Finding

Missing historical FX dependency detection compared `transactions.trade_currency` and
`portfolios.base_currency` as raw strings. Case or whitespace drift could falsely classify a
same-currency transaction as requiring historical FX enrichment, or emit non-canonical currency
codes into operator remediation samples.

That is a calculation-readiness risk because false missing-FX blockers can make valuation and
reporting readiness look worse than the underlying economics.

## Change

Added a repository-local currency-code SQL expression for operations queries. Missing-FX dependency
evidence now compares `upper(trim(...))` trade and portfolio currencies, selects canonical currency
codes in the sample query, and normalizes returned sample records.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
3. `python -m pytest tests/unit/services/query_service/repositories -q`
4. `python -m pytest tests/unit/services/query_service/services -q`
5. `git diff --check`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is a
calculation-readiness hardening slice that prevents currency-code formatting drift from creating
false missing-FX evidence.
