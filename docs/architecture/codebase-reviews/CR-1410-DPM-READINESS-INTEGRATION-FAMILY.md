# CR-1410 DPM Readiness Integration Family

## Status

In progress on 2026-07-06.

## Scope

`IntegrationService` DPM source-readiness contract family in `query_service`.

## Finding

GitHub issue #548 remains valid: `IntegrationService` still exposes many source-data product
methods through one broad facade. The DPM readiness path had already moved response assembly into
focused resolver modules, but the facade still owned the DPM reader dependency graph and direct
delegation for mandate binding, model targets, instrument eligibility, tax lots, market-data
coverage, and readiness orchestration.

That kept a cohesive contract family coupled to the full integration facade and made tests reach
through `IntegrationService` when the behavior under test only needed DPM readiness dependencies.

## Action

Added `DpmReadinessIntegrationService` as the DPM source-readiness contract-family boundary. The
new service owns repository-provider access, page-token adapter wiring for tax lots, DPM readiness
reader composition, and the DPM readiness source-data method group.

`IntegrationService` now constructs the family service from its existing dependency bundle and
keeps the public facade methods as thin compatibility delegates. Route handlers, request DTOs,
response DTOs, repository SQL, source-data product names, page-token encoding, and readiness
supportability semantics are unchanged.

## Compatibility

No downstream API contract changes are intended in this slice. Existing consumers can keep calling
the same integration routes and service facade methods. The extraction only narrows internal
ownership so future DPM readiness changes can be tested without the full integration facade.

## Remaining Issue Scope

This is a partial issue #548 slice. Additional contract-family extractions are still needed before
the issue should be marked fixed-local, including benchmark/reference products, external hedge
products, tax/performance economics products, and remaining market/reference families.

## No Wiki Change

No repo wiki update is required for this slice. The change is an internal service decomposition and
does not alter API shape, operator commands, source-data product contracts, migration policy, or
published runbooks.

## Validation

Local validation:

```powershell
python -m pytest tests\unit\services\query_service\services\test_integration_service.py -q
python -m ruff check src\services\query_service\app\services\integration_service.py src\services\query_service\app\services\dpm_readiness_integration_service.py tests\unit\services\query_service\services\test_integration_service.py --ignore E501,I001
python -m ruff format --check src\services\query_service\app\services\integration_service.py src\services\query_service\app\services\dpm_readiness_integration_service.py tests\unit\services\query_service\services\test_integration_service.py
python -m mypy src\services\query_service\app\services\integration_service.py src\services\query_service\app\services\dpm_readiness_integration_service.py
git diff --check
```
