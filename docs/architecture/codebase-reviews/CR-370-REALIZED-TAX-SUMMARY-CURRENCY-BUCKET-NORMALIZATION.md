# CR-370: Realized Tax Summary Currency Bucket Normalization

Date: 2026-05-28

## Scope

Query-service `PortfolioRealizedTaxSummary` aggregation and reporting-currency restatement.

## Finding

`TransactionService.get_realized_tax_summary(...)` aggregated realized tax evidence by raw
transaction currency. Source rows carrying equivalent values such as `USD` and ` usd ` could be
reported as separate ledger-currency totals, increasing FX restatement work and making the
implementation-backed tax summary less deterministic for downstream consumers.

The response also echoed raw portfolio base currency and requested reporting currency values even
though the conversion helper already used canonical currency codes internally.

## Change

Reused the shared query-service currency normalizer for:

1. realized tax summary base currency,
2. requested reporting currency,
3. realized tax evidence aggregation buckets,
4. reporting-currency conversion calls.

Equivalent source currency aliases now aggregate into one canonical ledger-currency total and the
response exposes canonical currency codes.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_transaction_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/transaction_service.py tests/unit/services/query_service/services/test_transaction_service.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a calculation-path
aggregation reliability hardening slice for the existing realized tax source-data product.
