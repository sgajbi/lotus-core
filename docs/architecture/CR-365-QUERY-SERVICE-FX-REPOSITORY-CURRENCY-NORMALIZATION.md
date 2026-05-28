# CR-365: Query-Service FX Repository Currency Normalization

Date: 2026-05-27

## Scope

Query-service transaction and reporting repository FX conversion lookups.

## Finding

`TransactionRepository.get_latest_fx_rate(...)` and
`ReportingRepository.get_latest_fx_rate(...)` used caller-provided currency codes for same-currency
short-circuit checks and FX-rate predicates. Padded or lower-case currency values could bypass the
identity conversion path, create unnecessary database work, or miss available canonical FX-rate
rows.

This mattered because these repositories support portfolio transaction totals, reporting views, and
cash/position conversion flows where calculation reliability depends on stable reference-data
lookup semantics.

## Change

Added a shared query-service repository currency-code normalizer and applied it before:

1. same-currency identity checks,
2. `FxRate.from_currency` predicates,
3. `FxRate.to_currency` predicates.

The SQL remains index-friendly because normalized constants are compared directly to persisted
currency columns; no column-side functions were introduced.

Updated transaction and reporting repository tests so padded lower-case source values prove both
identity conversion short-circuit behavior and canonical cross-currency query predicates.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_transaction_repository.py tests/unit/services/query_service/repositories/test_reporting_repository.py -q`
2. `python -m pytest tests/unit/services/query_service/repositories -q`
3. `python -m ruff check src/services/query_service/app/repositories/currency_codes.py src/services/query_service/app/repositories/transaction_repository.py src/services/query_service/app/repositories/reporting_repository.py tests/unit/services/query_service/repositories/test_transaction_repository.py tests/unit/services/query_service/repositories/test_reporting_repository.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a calculation-path
reliability and query-efficiency hardening slice for query-service FX conversion repositories.
