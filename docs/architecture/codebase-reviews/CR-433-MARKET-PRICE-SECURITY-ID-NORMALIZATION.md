# CR-433: Market Price Security-ID Normalization

Date: 2026-05-28

## Scope

Query-service market price service and repository lookup by security identifier.

## Finding

Market price lookup filtered `market_prices.security_id` by raw equality and returned the request
identifier as supplied. A padded request or persisted market-price identifier could miss available
price observations or leak a non-canonical identifier into the response.

That is a valuation and freshness evidence risk because price lookup supports holdings valuation,
simulation, market-data coverage, and operational diagnostics.

## Change

Reused the shared query-service security identifier normalizer at the market-price service and
repository boundaries. The service now calls the repository and returns the response with a
canonical security identifier. The repository now trims the request identifier, fails closed for a
blank identifier without querying, and filters against `trim(market_prices.security_id)`.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_price_repository.py tests/unit/services/query_service/services/test_price_service.py -q`
2. `python -m ruff check src/services/query_service/app/repositories/price_repository.py src/services/query_service/app/services/price_service.py tests/unit/services/query_service/repositories/test_price_repository.py tests/unit/services/query_service/services/test_price_service.py`
3. `python -m pytest tests/unit/services/query_service/repositories -q`
4. `python -m pytest tests/unit/services/query_service/services -q`
5. `git diff --check`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is a valuation
input hardening slice that prevents harmless source identifier padding from hiding market-price
evidence or leaking non-canonical response identity.
