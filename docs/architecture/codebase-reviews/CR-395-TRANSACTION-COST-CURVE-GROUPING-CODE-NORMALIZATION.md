# CR-395: Transaction Cost Curve Grouping-Code Normalization

Date: 2026-05-28

## Scope

Query-service `TransactionCostCurve:v1` source-data product grouping.

## Finding

Transaction-cost curve grouping keyed rows by raw `security_id` and `upper()`-only transaction type
and currency values. Padded source values such as ` buy ` or ` usd ` could split otherwise
equivalent cost evidence into separate curve points, distorting observation counts, weighted-average
cost bps, min/max cost bps, and supportability coverage.

## Change

Trimmed `security_id` and trimmed plus uppercased transaction type and currency in the
transaction-cost curve grouping key. Updated grouping coverage so a padded lower-case BUY/USD row
still aggregates into the canonical BUY/USD curve point.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_integration_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/integration_service.py tests/unit/services/query_service/services/test_integration_service.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a source-data
product calculation correctness and evidence aggregation slice.
