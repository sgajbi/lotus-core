# RFC-087 Slice 5 Evidence - Discretionary Mandate Binding

## Scope Proven

Slice 5 implements `DiscretionaryMandateBinding:v1` as a governed `lotus-core` source-data product
for `lotus-manage` stateful discretionary portfolio-management source assembly.

Implemented scope:

1. `portfolio_mandate_bindings` persistence with effective dating, binding versioning, source
   lineage, quality status, and portfolio foreign key.
2. `POST /ingest/mandate-bindings` for idempotent mandate binding ingestion.
3. `POST /integration/portfolios/{portfolio_id}/mandate-binding` for deterministic
   point-in-time resolution.
4. Source-data product catalog, source-security profile, route-family registry, domain-product
   declaration, OpenAPI extensions, and canonical seed updates.
5. Canonical front-office seed data for `PB_SG_GLOBAL_BAL_001` binding
   `MANDATE_PB_SG_GLOBAL_BAL_001` to `MODEL_PB_SG_GLOBAL_BAL_DPM` and
   `POLICY_DPM_SG_BALANCED_V1`.

## Endpoint Contract

| Route | Plane | Purpose |
| --- | --- | --- |
| `POST /ingest/mandate-bindings` | ingestion | Upsert effective-dated discretionary mandate bindings from mandate administration or policy systems. |
| `POST /integration/portfolios/{portfolio_id}/mandate-binding` | query control plane | Resolve portfolio mandate, model, policy, authority, jurisdiction, booking center, tax-awareness, settlement-awareness, and rebalance constraints for downstream `lotus-manage` source assembly. |

The control-plane response includes source-data runtime metadata, `supportability`, and `lineage`.
Inactive authority or missing policy pack is surfaced as `INCOMPLETE` supportability rather than
being hidden by local fallback truth.

## Local Validation

Focused proof commands:

```powershell
python -m pytest tests/unit/services/ingestion_service/test_reference_data_dto.py tests/unit/services/ingestion_service/test_reference_data_ingestion_service.py tests/unit/services/query_service/repositories/test_reference_data_repository.py tests/unit/services/query_service/services/test_integration_service.py tests/unit/services/query_control_plane_service/routers/test_integration_router.py tests/unit/libs/portfolio-common/test_source_data_products.py tests/unit/libs/portfolio-common/test_source_data_security.py tests/unit/test_domain_data_product_contracts.py tests/unit/tools/test_front_office_portfolio_seed.py -q
```

Result: `170 passed`.

OpenAPI and router proof:

```powershell
python -m pytest tests/integration/services/query_control_plane_service/test_integration_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py::test_openapi_contains_control_plane_endpoints tests/integration/services/query_control_plane_service/test_control_plane_app.py::test_openapi_fully_documents_dpm_model_portfolio_target_schema_family tests/integration/services/query_control_plane_service/test_control_plane_app.py::test_openapi_fully_documents_dpm_mandate_binding_schema_family tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py::test_openapi_describes_reference_data_shared_schema -q
```

Result: `35 passed`.

Governance gates:

```powershell
make openapi-gate
make api-vocabulary-gate
make source-data-product-contract-guard
make route-contract-family-guard
make domain-product-validate
```

Results:

1. OpenAPI quality gate passed.
2. API vocabulary inventory validation passed.
3. Source-data product contract guard passed.
4. Route contract-family guard passed.
5. Repo-native domain-product validation passed.

## Pending Live Evidence

Live canonical proof remains pending until the running front-office stack is refreshed with this
branch. Required live check:

1. seed or refresh canonical data,
2. call `POST /integration/portfolios/PB_SG_GLOBAL_BAL_001/mandate-binding` with
   `{"as_of_date":"2026-04-10"}`,
3. verify `product_name = DiscretionaryMandateBinding`, `supportability.state = READY`,
   `model_portfolio_id = MODEL_PB_SG_GLOBAL_BAL_DPM`, and
   `policy_pack_id = POLICY_DPM_SG_BALANCED_V1`,
4. verify `lotus-manage` consumes the binding as a source product rather than inferring mandate
   truth locally.

## Deliberate Non-Claims

This slice does not enable full `lotus-manage` stateful execution. Eligibility, tax-lot, market-data
coverage, DPM readiness, and complete live canonical proof remain future RFC-087 slices.
