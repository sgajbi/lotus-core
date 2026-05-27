# CR-367: Query-Service FX Conversion Cache Currency Normalization

Date: 2026-05-28

## Scope

Query-service service-layer FX conversion helpers for transaction, reporting, cash-balance, and
core-snapshot flows.

## Finding

After repository FX lookups were hardened, service-layer conversion helpers still built
same-currency checks, cache keys, repository calls, and error messages from raw caller currency
codes. Padded or lower-case values could:

1. bypass same-currency identity conversion and perform avoidable repository work,
2. fragment FX conversion caches across padded aliases,
3. emit non-canonical missing-FX diagnostics.

These helpers sit on calculation-facing product paths for transactions, reporting, cash balances,
and core snapshots, so caller-boundary normalization belongs at this layer as well as in the
repositories.

## Change

Reused the shared query-service currency normalizer in:

1. `TransactionService._convert_amount(...)` and `_get_fx_rate(...)`,
2. `ReportingService._convert_amount(...)` and `_get_fx_rate(...)`,
3. `CashBalanceService._convert_amount(...)` and `_get_fx_rate(...)`,
4. `CoreSnapshotService._get_fx_rate_or_raise(...)`.

The services now normalize before same-currency checks, FX cache-key construction, repository calls,
and missing-FX diagnostics.

Added direct service tests proving padded same-currency inputs short-circuit without repository
lookups and padded/canonical cross-currency calls share one canonical cache entry.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_transaction_service.py tests/unit/services/query_service/services/test_reporting_service.py tests/unit/services/query_service/services/test_cash_balance_service.py tests/unit/services/query_service/services/test_core_snapshot_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/transaction_service.py src/services/query_service/app/services/reporting_service.py src/services/query_service/app/services/cash_balance_service.py src/services/query_service/app/services/core_snapshot_service.py tests/unit/services/query_service/services/test_transaction_service.py tests/unit/services/query_service/services/test_reporting_service.py tests/unit/services/query_service/services/test_cash_balance_service.py tests/unit/services/query_service/services/test_core_snapshot_service.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a service-layer
calculation reliability and cache-efficiency hardening slice.
