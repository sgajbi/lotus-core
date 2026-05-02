# RFC-087 Slice 3 Evidence - DPM Governance Scaffold

Date: 2026-05-02

## Scope Completed

Slice 3 establishes the governed product, security, and domain-product contract posture for the
DPM source products required by `lotus-manage` RFC-0036. It does not expose runtime API routes.

Implemented governance scaffold:

1. Added proposed DPM source products to
   `portfolio_common.source_data_products.DPM_PLANNED_SOURCE_DATA_PRODUCT_CATALOG`:
   - `DpmModelPortfolioTarget:v1`
   - `DiscretionaryMandateBinding:v1`
   - `InstrumentEligibilityProfile:v1`
   - `PortfolioTaxLotWindow:v1`
   - `MarketDataCoverageWindow:v1`
2. Added planned source-security profiles in
   `portfolio_common.source_data_security.DPM_PLANNED_SOURCE_DATA_SECURITY_PROFILES`.
3. Added repo-native proposed domain-product declarations in
   `contracts/domain-data-products/lotus-core-products.v1.json`.
4. Added platform domain-vocabulary identifiers required by the DPM product declarations:
   - `model_portfolio_id`
   - `currency_pair`
5. Added unit tests proving the planned products are governed, `lotus-manage`-scoped, not part of
   the active route catalog, and aligned with source-security policy.
6. Updated the repo-local wiki source to show the proposed DPM product set without claiming
   runtime availability.

## Route Exposure Decision

No route-family registry entries were added in this slice because the local
`route_contract_family_guard` correctly requires registered routes to be implemented by active
FastAPI routers. Registering planned route paths before the endpoint slices would weaken the guard
and create false route truth.

The planned route families are instead held in:

1. `DPM_PLANNED_SOURCE_DATA_PRODUCT_CATALOG`,
2. `contracts/domain-data-products/lotus-core-products.v1.json` with `lifecycle_status:
   "proposed"`,
3. `docs/standards/rfc-087-dpm-source-product-spec.v1.json`.

Each endpoint slice must promote its product from planned/proposed to active and add the concrete
route-family registry entry only when the router, OpenAPI metadata, source-security extension,
tests, and live proof are present.

## Validation

Focused validation run locally:

```text
python -m pytest tests/unit/libs/portfolio-common/test_source_data_products.py tests/unit/libs/portfolio-common/test_source_data_security.py tests/unit/docs/test_rfc087_dpm_source_product_spec.py -q
39 passed in 0.33s

python -m ruff check src/libs/portfolio-common/portfolio_common/source_data_products.py src/libs/portfolio-common/portfolio_common/source_data_security.py tests/unit/libs/portfolio-common/test_source_data_products.py tests/unit/libs/portfolio-common/test_source_data_security.py tests/unit/docs/test_rfc087_dpm_source_product_spec.py --ignore E501,I001
All checks passed!

python -m ruff format --check src/libs/portfolio-common/portfolio_common/source_data_products.py src/libs/portfolio-common/portfolio_common/source_data_security.py tests/unit/libs/portfolio-common/test_source_data_products.py tests/unit/libs/portfolio-common/test_source_data_security.py tests/unit/docs/test_rfc087_dpm_source_product_spec.py
5 files already formatted

make source-data-product-contract-guard
Source-data product contract guard passed.

make route-contract-family-guard
Route contract-family guard passed.

make domain-product-validate
Validated 1 repo-native producer declaration(s) and 0 repo-native consumer declaration(s) in C:\Users\Sandeep\projects\lotus-core\contracts\domain-data-products
```

## Critical Review

The active source-data catalog remains unchanged, which is intentional. Existing guards continue to
protect current API truth, while the planned DPM catalog gives subsequent endpoint slices a single
typed source for names, routes, serving plane, consumers, and paging/export posture.

The security profiles are deliberately system-access profiles because these DPM source products are
analytics input products consumed by `lotus-manage`, not broad business-consumer read APIs. Client
sensitive products still carry PII declarations and client-record retention requirements.

The domain-product declarations are marked `proposed`; they are not implementation-backed runtime
features yet. Endpoint slices must not move them to `active` until API, ingestion, OpenAPI,
observability, tests, and live evidence are complete.

## Residual Work For Later Slices

1. Promote each product to active only in its implementation slice.
2. Add concrete route-family registry entries when each route exists.
3. Add source-data OpenAPI extensions on each implemented route.
4. Add trust telemetry evidence fixtures when runtime proof exists.
5. Seed the canonical managed mandate portfolio after source pipelines and APIs are implemented.
