# RFC-087 Slice 7 Evidence - Portfolio Tax-Lot Window

## Scope

Slice 7 implements `PortfolioTaxLotWindow:v1` as a governed `lotus-core` source-data product for
tax-aware `lotus-manage` DPM source assembly.

Implemented scope:

1. `POST /integration/portfolios/{portfolio_id}/tax-lots` on the query control plane,
2. portfolio-window tax-lot retrieval from existing `position_lot_state`,
3. deterministic cursor paging by `acquisition_date` and `lot_id`,
4. optional `security_ids`, `lot_status_filter`, and `include_closed_lots` controls,
5. lot-level cost basis, local currency, source transaction, calculation policy lineage, and
   supportability,
6. source-data product catalog, source-security profile, route-family registry, domain-product
   declaration, OpenAPI schema, and endpoint tests.

This slice deliberately does not introduce a new tax-lot ingestion endpoint. Existing core BUY and
lot-state processing remain the current authority. A separate ingestion product should be added
only if a custody or tax-lot engine feed becomes the enterprise source of record.

## Endpoint Contract

| Route | Plane | Purpose |
| --- | --- | --- |
| `POST /integration/portfolios/{portfolio_id}/tax-lots` | query control plane | Resolve portfolio-window tax lots and cost basis for tax-aware DPM sell decisions without production per-security fan-out. |

The response includes the source-data runtime envelope, paged `lots`, `page` metadata,
`supportability`, and core lineage. The endpoint is an analytics-input source product for
downstream source assembly. It is not a transaction history endpoint and does not replace booking
or trade-ledger reads.

## Local Validation

Focused unit proof:

```powershell
python -m pytest tests/unit/services/query_service/repositories/test_buy_state_repository.py tests/unit/services/query_service/services/test_integration_service.py tests/unit/services/query_control_plane_service/routers/test_integration_router.py tests/unit/libs/portfolio-common/test_source_data_products.py tests/unit/libs/portfolio-common/test_source_data_security.py tests/unit/test_domain_data_product_contracts.py -q
```

Result: `111 passed`.

OpenAPI proof:

```powershell
python -m pytest tests/integration/services/query_control_plane_service/test_control_plane_app.py::test_openapi_contains_control_plane_endpoints tests/integration/services/query_control_plane_service/test_control_plane_app.py::test_openapi_fully_documents_dpm_portfolio_tax_lot_schema_family -q
```

Result: `2 passed`.

Governance proof:

```powershell
make openapi-gate
make api-vocabulary-gate
make source-data-product-contract-guard
make route-contract-family-guard
make domain-product-validate
python scripts/temporal_vocabulary_guard.py
make lint
make migration-smoke
git diff --check
..\lotus-platform\automation\Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core
```

Results:

1. OpenAPI quality gate passed.
2. API vocabulary inventory validation passed.
3. Source-data product contract guard passed.
4. Route contract-family guard passed.
5. Repo-native domain-product validation passed.
6. Temporal vocabulary guard passed.
7. `make lint` passed after formatting the touched source-data security test file.
8. Migration smoke passed in `alembic-sql` mode. No migration is introduced by this slice.
9. `git diff --check` passed.
10. Wiki check-only reported expected publication drift for `Mesh-Data-Products.md` because the
    repo-authored wiki source has been updated and is not yet published to the GitHub wiki.

## Critical Behavior Covered

Tests cover:

1. portfolio existence lookup and `404` router mapping,
2. repository query shape for portfolio, as-of date, open/closed filters, cursor, ordering, and
   transaction-currency join,
3. page-size plus one retrieval and next-token generation,
4. page-token scope mismatch rejection,
5. missing requested securities surfaced as `INCOMPLETE`,
6. partial pages surfaced as `DEGRADED` with `TAX_LOTS_PAGE_PARTIAL` so later-page securities are
   not falsely reported missing,
7. OpenAPI schema documentation completeness for request, record, supportability, response, and
   pagination models,
8. active source-data catalog, source-security, route-family, and domain-product declarations.

## Current Evidence Status

Local implementation evidence is complete for the producer API and mesh contract posture. Live
canonical stack evidence is pending until the running stack is refreshed with this branch.

Required live proof after refresh:

1. seed or refresh canonical data for `PB_SG_GLOBAL_BAL_001`,
2. call `POST /integration/portfolios/PB_SG_GLOBAL_BAL_001/tax-lots` with
   `{"as_of_date":"2026-04-10","page":{"page_size":250}}`,
3. verify `product_name = PortfolioTaxLotWindow`,
4. verify lot rows include expected held securities, cost basis, local currency, and source
   transaction lineage,
5. verify `lotus-manage` consumes the source product for tax-aware execution instead of looping over
   per-security lot reads or inferring cost basis locally.

## Non-Claims

This slice does not implement market-data/FX coverage, DPM source readiness, or full
`lotus-manage` stateful execution. It also does not claim live canonical proof until the refreshed
runtime is available and the endpoint is exercised against seeded canonical data.
