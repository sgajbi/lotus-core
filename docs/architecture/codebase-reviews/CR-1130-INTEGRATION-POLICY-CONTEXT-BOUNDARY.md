# CR-1130 Integration Policy Context Boundary

Date: 2026-06-21

## Scope

Query-service integration snapshot policy context resolution in
`src/services/query_service/app/services/integration_policy.py`.

## Finding

`resolve_policy_context(...)` and `build_effective_policy_response(...)` were API-facing policy
helpers for the effective integration policy surface. They preserved the correct response behavior,
but concentrated default/global/tenant policy precedence, strict-mode provenance, allowed-section
warnings, requested-section filtering, and response assembly in branch-heavy helpers.

Radon reported:

- `resolve_policy_context`: `C (11)`
- `build_effective_policy_response`: `B (8)`

## Action Taken

Extracted focused helpers for:

- default policy-context construction,
- global consumer section override,
- tenant policy lookup,
- tenant consumer/default-section resolution,
- tenant matched-rule IDs,
- tenant strict-mode-only provenance,
- missing allowed-section warning posture,
- effective requested-section filtering.

The public functions, environment-backed policy loading, canonical consumer mapping, strict-mode
behavior, matched-rule IDs, warnings, and response DTO shape remain unchanged.

## Evidence

Focused behavior proof:

- `python -m pytest tests\unit\services\query_service\services\test_integration_policy.py tests\unit\services\query_service\services\test_integration_service.py::test_canonical_consumer_system_mappings tests\unit\services\query_service\services\test_integration_service.py::test_load_policy_variants tests\unit\services\query_service\services\test_integration_service.py::test_normalize_and_resolve_consumer_sections tests\unit\services\query_service\services\test_integration_service.py::test_resolve_policy_context_default tests\unit\services\query_service\services\test_integration_service.py::test_resolve_policy_context_global_and_tenant tests\unit\services\query_service\services\test_integration_service.py::test_resolve_policy_context_tenant_default_sections_and_strict_mode_id tests\unit\services\query_service\services\test_integration_service.py::test_get_effective_policy_filters_requested_sections tests\unit\services\query_service\services\test_integration_service.py::test_get_effective_policy_no_allowed_restriction_passthrough tests\unit\services\query_service\services\test_integration_service.py::test_get_effective_policy_uses_configured_allowed_sections_when_unrequested -q`
- Result: `10 passed`

Focused static proof:

- `python -m ruff check src\services\query_service\app\services\integration_policy.py tests\unit\services\query_service\services\test_integration_policy.py tests\unit\services\query_service\services\test_integration_service.py`
- Result: passed

Focused type proof:

- `make typecheck`
- Result: passed

Focused complexity proof:

- `python -m radon cc src\services\query_service\app\services\integration_policy.py -s`
- Result: `resolve_policy_context` is `A (2)`, `build_effective_policy_response` is `A (2)`,
  and all functions/classes in `integration_policy.py` are A-ranked.

Focused maintainability proof:

- `python -m radon mi src\services\query_service\app\services\integration_policy.py -s`
- Result: `A (32.39)`

Measured movement:

- `resolve_policy_context`: `C (11)` -> `A (2)`
- `build_effective_policy_response`: `B (8)` -> `A (2)`
- `integration_policy.py` function-level complexity: no B-or-worse functions/classes remain

## Residual Risk

This slice does not change API contracts, OpenAPI, environment variable names, or tenant policy
semantics. Broader integration service modules remain large and should continue to be split only by
measured API/source-product risk.

## Bank-Buyable Control Movement

This slice improves:

- reviewability of tenant/global integration policy precedence,
- explicit provenance and warning posture for effective-policy responses,
- focused regression evidence for policy behavior used by downstream consumers.

It does not claim full bank-buyable readiness for `lotus-core`.
