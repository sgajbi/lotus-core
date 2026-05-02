# RFC-087 Slice 8 Evidence - Market Data Coverage Window

## Scope

Slice 8 implements `MarketDataCoverageWindow:v1` as a governed `lotus-core` source-data product for
stateful `lotus-manage` DPM market-data source assembly.

Implemented scope:

1. `POST /integration/market-data/coverage` on the query control plane,
2. latest instrument price coverage from existing `market_prices`,
3. latest FX coverage from existing `fx_rates`,
4. bounded request options for instrument ids, currency pairs, valuation currency, tenant context,
   and maximum staleness,
5. supportability diagnostics for missing and stale observations,
6. source-data product catalog, source-security profile, route-family registry, domain-product
   declaration, OpenAPI schema, and endpoint tests.

This slice deliberately does not add new market-price or FX ingestion endpoints. Existing
`POST /ingest/market-prices` and `POST /ingest/fx-rates` remain sufficient for first-wave DPM
coverage proof.

## Endpoint Contract

| Route | Plane | Purpose |
| --- | --- | --- |
| `POST /integration/market-data/coverage` | query control plane | Resolve held and target universe price/FX coverage for DPM valuation, drift, cash conversion, and rebalance sizing. |

The response includes the source-data runtime envelope, `price_coverage`, `fx_coverage`,
`supportability`, and core lineage. The endpoint is an analytics-input source product for
downstream source assembly. It is not a historical price-series or FX-series endpoint.

## Local Validation

Focused unit proof:

```powershell
python -m pytest tests/unit/services/query_service/repositories/test_reference_data_repository.py tests/unit/services/query_service/services/test_integration_service.py tests/unit/services/query_control_plane_service/routers/test_integration_router.py tests/unit/libs/portfolio-common/test_source_data_products.py tests/unit/libs/portfolio-common/test_source_data_security.py tests/unit/test_domain_data_product_contracts.py -q
```

Result: `121 passed`.

OpenAPI proof:

```powershell
python -m pytest tests/integration/services/query_control_plane_service/test_control_plane_app.py::test_openapi_contains_control_plane_endpoints tests/integration/services/query_control_plane_service/test_control_plane_app.py::test_openapi_fully_documents_dpm_market_data_coverage_schema_family -q
```

Result: `2 passed`.

Governance proof:

```powershell
make source-data-product-contract-guard
make route-contract-family-guard
make domain-product-validate
make openapi-gate
make api-vocabulary-gate
make lint
make migration-smoke
git diff --check
..\lotus-platform\automation\Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core
```

Result: source-data product contracts, route-family registry, domain data products, OpenAPI,
vocabulary, lint, migration smoke, and whitespace checks passed. Wiki check reported expected
authored-source drift for `Mesh-Data-Products.md` because this slice updates repo-local wiki truth
that will be published after merge.

## Critical Behavior Covered

Tests cover:

1. latest price and FX repository lookup contracts,
2. bounded request validation for duplicate instruments and currency pairs,
3. fresh price and FX observations classified as `READY`,
4. missing observations surfaced as `INCOMPLETE` with `MARKET_DATA_MISSING`,
5. stale-only observations surfaced as `DEGRADED` with `MARKET_DATA_STALE`,
6. router delegation and response shape,
7. OpenAPI schema documentation completeness for request, pair, coverage, supportability, and
   response models,
8. active source-data catalog, source-security, route-family, and domain-product declarations.

## Current Evidence Status

Local implementation evidence is complete for the producer API and mesh contract posture. Live
canonical stack evidence is pending until the running stack is refreshed with this branch.

Required live proof after refresh:

1. seed or refresh canonical prices and FX for the held and target universe,
2. call `POST /integration/market-data/coverage` with the canonical DPM instruments and required
   currency pairs,
3. verify `product_name = MarketDataCoverageWindow`,
4. verify coverage rows include all expected instruments and currency pairs,
5. verify stale and missing diagnostics are absent for the canonical ready case or explicitly
   bounded for a negative probe,
6. verify `lotus-manage` consumes the source product for market-data assembly instead of serial
   price/FX lookup loops.

## Non-Claims

This slice does not implement DPM source-family readiness, full `lotus-manage` stateful execution,
or live canonical proof. Those remain separate RFC-087/RFC-0036 closure requirements.
