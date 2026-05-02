# RFC-087 Slice 6 Evidence - Instrument Eligibility Profile

## Scope

Slice 6 implements `InstrumentEligibilityProfile:v1` for stateful `lotus-manage` DPM source
assembly. The slice covers:

1. `POST /ingest/instrument-eligibility`,
2. effective-dated `instrument_eligibility_profiles` persistence,
3. `POST /integration/instruments/eligibility-bulk`,
4. source-data catalog, source-security, route-family, and domain-product declarations,
5. canonical front-office seed data for held and target instruments.

## Contract

The bulk API resolves eligibility for a caller-provided security list and preserves request order.
Missing source records are returned explicitly as `UNKNOWN` with
`ELIGIBILITY_PROFILE_MISSING`; `lotus-manage` must not infer eligibility locally.

Returned records include:

1. buy/sell eligibility,
2. product shelf status,
3. bounded restriction reason codes,
4. settlement days and settlement calendar,
5. liquidity tier,
6. issuer and ultimate parent issuer,
7. asset class and country of risk,
8. source record id and source-data runtime metadata.

Free-text `restriction_rationale` is retained in core storage for operator audit but is not exposed
by the downstream DPM source API.

## Local Proof

Focused proof completed locally on this branch:

```powershell
python -m pytest tests/unit/services/ingestion_service/test_reference_data_dto.py tests/unit/services/ingestion_service/test_reference_data_ingestion_service.py tests/unit/services/query_service/repositories/test_reference_data_repository.py tests/unit/services/query_service/services/test_integration_service.py tests/unit/services/query_control_plane_service/routers/test_integration_router.py tests/unit/libs/portfolio-common/test_source_data_products.py tests/unit/libs/portfolio-common/test_source_data_security.py tests/unit/test_domain_data_product_contracts.py tests/unit/tools/test_front_office_portfolio_seed.py -q
python -m pytest tests/integration/services/query_control_plane_service/test_integration_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py::test_openapi_contains_control_plane_endpoints tests/integration/services/query_control_plane_service/test_control_plane_app.py::test_openapi_fully_documents_dpm_instrument_eligibility_schema_family tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py::test_openapi_describes_remaining_ingestion_operational_responses -q
make openapi-gate
make api-vocabulary-gate
make source-data-product-contract-guard
make route-contract-family-guard
make domain-product-validate
make migration-smoke
```

Results:

| Check | Result |
| --- | --- |
| Focused unit slice | Passed, 178 tests |
| Focused integration/OpenAPI slice | Passed, 34 tests |
| `make openapi-gate` | Passed |
| `make api-vocabulary-gate` | Passed |
| `make source-data-product-contract-guard` | Passed |
| `make route-contract-family-guard` | Passed |
| `make domain-product-validate` | Passed |
| `python scripts/temporal_vocabulary_guard.py` | Passed |
| `make migration-smoke` | Passed |
| `make lint` | Passed |
| `git diff --check` | Passed |

## Current Evidence Status

Local implementation evidence is complete for source contracts, tests, and seed data. Live
canonical stack evidence is pending until the running front-office stack is refreshed with this
branch.

## Non-Claims

This slice does not implement tax-lot, market-data/FX coverage, or full DPM source-family readiness
products. Stateful `lotus-manage` execution remains intentionally gated until the remaining RFC-087
source products are implemented and proven live.
