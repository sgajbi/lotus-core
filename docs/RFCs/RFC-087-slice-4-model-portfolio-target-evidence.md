# RFC-087 Slice 4 Evidence - Model Portfolio Target Pipeline And API

Date: 2026-05-02

## Scope Proven

Slice 4 implemented the first active DPM source-data product in `lotus-core`:

1. ingestion DTOs and routes for model portfolio definitions and target rows,
2. durable model portfolio definition and target persistence tables,
3. effective-dated repository resolution for approved model versions and active targets,
4. `POST /integration/model-portfolios/{model_portfolio_id}/targets`,
5. active source-data product catalog, source-security profile, route-family, and
   domain-product declaration alignment for `DpmModelPortfolioTarget:v1`,
6. canonical front-office seed extension for the governed managed mandate portfolio model target
   universe.

## Implemented Routes

| Route | Plane | Purpose |
| --- | --- | --- |
| `POST /ingest/model-portfolios` | ingestion | Upsert effective-dated model portfolio definitions, approvals, and lineage. |
| `POST /ingest/model-portfolio-targets` | ingestion | Upsert effective-dated model target rows and min/max bands. |
| `POST /integration/model-portfolios/{model_portfolio_id}/targets` | query control plane | Resolve approved DPM model target weights for downstream `lotus-manage` source assembly. |

## Critical Behavior Covered

1. target band validation rejects invalid `min_weight`, `target_weight`, `max_weight` ordering,
2. model target ingestion rejects duplicate model/version/instrument/effective-date records,
3. ingestion service uses deterministic conflict keys for definitions and target rows,
4. repository lookup filters to approved effective model definitions,
5. target lookup returns latest effective rows by instrument and excludes inactive targets by
   default,
6. query service returns `READY`, `DEGRADED`, or `INCOMPLETE` supportability based on target
   completeness and total weight,
7. router maps missing approved model data to a documented 404,
8. OpenAPI exposes source-data product and source-security metadata for the active route,
9. canonical front-office seed includes `MODEL_PB_SG_GLOBAL_BAL_DPM` version `2026.04` with
   target weights summing to `1.0000000000`.

## Validation Evidence

Commands run from `C:\Users\Sandeep\projects\lotus-core`:

1. `python -m pytest tests/unit/libs/portfolio-common/test_source_data_products.py tests/unit/libs/portfolio-common/test_source_data_security.py tests/unit/test_domain_data_product_contracts.py tests/unit/services/ingestion_service/test_reference_data_dto.py tests/unit/services/ingestion_service/test_reference_data_ingestion_service.py tests/unit/services/query_service/repositories/test_reference_data_repository.py tests/unit/services/query_service/services/test_integration_service.py tests/unit/services/query_control_plane_service/routers/test_integration_router.py tests/integration/services/query_control_plane_service/test_integration_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py -q`
   - Result: `181 passed`.
2. `python -m pytest tests/unit/tools/test_front_office_portfolio_seed.py -q`
   - Result: `38 passed`.
3. `python -m ruff check ...`
   - Result: passed for all touched implementation and test files.
4. `python -m ruff format --check ...`
   - Result: `16 files already formatted` for the touched Slice 4 set.
5. `make route-contract-family-guard`
   - Result: passed.
6. `make source-data-product-contract-guard`
   - Result: passed.
7. `make domain-product-validate`
   - Result: validated `1` repo-native producer declaration.
8. `make ingestion-contract-gate`
   - Result: passed.
9. `make openapi-gate`
   - Result: passed.
10. `make api-vocabulary-gate`
    - Result: passed.
11. `make migration-smoke`
    - Result: migration contract check passed in `alembic-sql` mode.

## Remaining Live Evidence

Live canonical stack proof is still pending until the running front-office canonical stack is
refreshed with this branch. The local implementation now contains the seed data and API surface
needed for that proof:

1. reseed core through the governed front-office seed path,
2. call `POST /integration/model-portfolios/MODEL_PB_SG_GLOBAL_BAL_DPM/targets` with
   `{"as_of_date": "2026-04-10"}`,
3. verify a `DpmModelPortfolioTarget:v1` response with `READY` supportability and total target
   weight `1.0000000000`,
4. then wire `lotus-manage` RFC-0036 source assembly to this endpoint.

No final Slice 4 closure should claim live proof until those runtime steps pass.
