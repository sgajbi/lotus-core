# CR-016 Pure HTTP Bootstrap Review

## Scope

Pure HTTP/control-plane app bootstrap in:

- `query_service`
- `query_control_plane_service`
- `event_replay_service`
- `financial_reconciliation_service`
- `ingestion_service`

## Findings

These services repeat a large shared bootstrap pattern:

- FastAPI app construction
- Prometheus `/metrics` exposure
- OpenAPI generation with metrics content override and schema enrichment
- correlation/request/trace header middleware
- HTTP observability middleware
- unhandled exception normalization
- health router inclusion

This is a real maintainability seam, not just superficial similarity.

The duplication is already carrying some cost:

- the same correlation/observability/exception behavior is maintained in
  multiple apps
- review and hardening work must be repeated app by app
- future drift risk is high

## Actions taken

Extracted the shared bootstrap behavior into:

- `portfolio_common.http_app_bootstrap.configure_standard_http_app(...)`
- `portfolio_common.http_app_bootstrap.configure_standard_openapi(...)`
- `portfolio_common.http_app_bootstrap.include_routers(...)`

Migrated:

- `query_service`
- `query_control_plane_service`
- `event_replay_service`
- `financial_reconciliation_service`
- `ingestion_service`

The helper preserves service-local ownership for:

- enterprise middleware
- startup/lifespan behavior
- dependency-critical startup policy
- health dependency set
- router selection

## Design boundary

This was safe to refactor because the shared layer is now explicit, while the
service-specific contracts remain local. The helper is intentionally not an app
factory.

The service-local code still owns:

- `FastAPI(...)` construction
- lifespan logic
- enterprise policy hooks
- Kafka fail-fast behavior in `ingestion_service`
- health dependency declaration
- router inclusion choices

## Follow-up

If future apps need this same pattern, extend the helper only at the shared
middleware/OpenAPI/router-registration layer.

Do not collapse service-local startup contracts into the helper unless the
contract is genuinely identical.

## Evidence

- `src/libs/portfolio-common/portfolio_common/http_app_bootstrap.py`
- `src/services/query_service/app/main.py`
- `src/services/query_control_plane_service/app/main.py`
- `src/services/event_replay_service/app/main.py`
- `src/services/financial_reconciliation_service/app/main.py`
- `src/services/ingestion_service/app/main.py`
