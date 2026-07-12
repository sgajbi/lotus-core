# CR-1399 Capability Policy Source Boundary

## Objective

Fix GitHub issue #549 by separating Core integration capability catalog policy, tenant override
parsing, environment/config loading, policy resolution, and API response assembly into explicit
boundaries.

## Expected Improvement

- Capability graph and workflow dependency logic can be tested with in-memory policy inputs and no
  environment variables.
- Tenant override JSON parsing can be tested independently from response assembly.
- Environment/settings access is isolated to `EnvironmentCapabilityPolicySource`.
- `CapabilitiesService` remains a thin use-case facade around policy loading, policy resolution,
  business-date lookup, and response assembly.
- The change improves design modularity inside the existing query/control-plane deployable; no
  runtime service split is justified.

## Scope

- Added `query_service.app.services.capability_policy` with:
  - `CapabilityCatalog`
  - `CapabilityPolicyInputs`
  - `EnvironmentCapabilityPolicySource`
  - `CapabilityPolicyResolver`
  - `CapabilitiesResponseAssembler`
  - tenant override decode/normalize helpers
- Reduced `CapabilitiesService` to dependency composition, `as_of_date` resolution, and the public
  `get_integration_capabilities(...)` orchestration method.
- Added focused unit tests for env-free policy resolution and standalone tenant override parsing.

## Behavior And Compatibility

No route path, request parameter, response DTO field, OpenAPI schema, database schema, environment
variable name, policy version default, tenant override JSON shape, or deployment topology changed.
Existing capability endpoint output remains compatible.

## Validation Evidence

- `python -m pytest tests\unit\services\query_service\services\test_capabilities_service.py -q`
  - `14 passed`
- `python -m ruff check src\services\query_service\app\services\capability_policy.py src\services\query_service\app\services\capabilities_service.py tests\unit\services\query_service\services\test_capabilities_service.py`
  - passed

Final lint, documentation, and diff checks are recorded in the issue comment before commit.

## Documentation And Guidance Decision

- Repo context updated because future capability endpoints and policy surfaces should isolate
  source/config loading from policy resolution and response assembly.
- Codebase review ledger updated with this hardened boundary.
- No wiki update: no operator command, public endpoint usage, or runbook truth changed.
- No platform skill update: existing backend delivery and codebase review skills already require
  reusable boundaries plus repo context updates for repeated issue patterns.
