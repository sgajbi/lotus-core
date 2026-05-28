# CR-372: Allocation Bucket Dimension Canonicalization

Date: 2026-05-28

## Scope

Query-service allocation calculation bucket keys for AUM and asset-allocation reporting products.

## Finding

`calculate_allocation_views(...)` used raw instrument dimension values as allocation bucket keys.
Source values such as `EQUITY` and ` equity `, `USD` and ` usd `, or `US` and ` us ` could split
exposure totals across duplicate buckets even though they represent the same private-banking
classification. Region resolution had the same whitespace sensitivity for country codes.

This mattered because allocation buckets are calculation outputs used for portfolio review,
exposure analysis, advisory context, and downstream reporting.

## Change

Added dimension-aware allocation bucket canonicalization:

1. trim all bucket-key values,
2. uppercase controlled-code dimensions such as asset class, currency, sector, country,
   rating, issuer id, and ultimate parent issuer id,
3. preserve trimmed display casing for product-type and issuer-name dimensions,
4. trim country codes before region mapping.

The calculation now aggregates equivalent controlled vocabulary aliases into one deterministic
bucket while preserving human-readable product-type and issuer-name values.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_allocation_calculator.py tests/unit/services/query_service/services/test_reporting_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/allocation_calculator.py src/services/query_service/app/services/reporting_classification.py tests/unit/services/query_service/services/test_allocation_calculator.py tests/unit/services/query_service/services/test_reporting_service.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a calculation-output
reliability hardening slice for existing allocation reporting products.
