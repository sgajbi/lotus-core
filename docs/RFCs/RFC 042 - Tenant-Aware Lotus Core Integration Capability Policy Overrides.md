# RFC 042 - Tenant-Aware lotus-core Integration Capability Policy Overrides

- Status: IMPLEMENTED
- Date: 2026-02-24
- Owners: lotus-core Query Service

## Context

`GET /integration/capabilities` is the contract used by lotus-gateway/UI and peer services
to understand lotus-core feature/workflow availability. The previous implementation only
supported global environment flags and one global policy version, which limited:

- tenant-specific rollout control,
- backend-driven configurability depth,
- productized operating modes across clients.

## Decision

Add tenant-aware policy overrides to lotus-core capabilities resolution via:

- `LOTUS_CORE_CAPABILITY_TENANT_OVERRIDES_JSON` environment variable.

The service now resolves capabilities in this order:

1. Global feature defaults from existing env flags.
2. Tenant override block (if configured).
3. Consumer-specific `supported_input_modes` override (with `default` fallback).

Supported tenant override keys:

- `policy_version`
- `features` (map: feature key -> boolean)
- `workflows` (map: workflow key -> boolean)
- `supported_input_modes` (map: consumer system key -> list of input modes)

## Rationale

- Keeps configurability in lotus-core backend, not in lotus-gateway/UI.
- Improves integration readiness for multi-tenant deployments.
- Preserves stable contract shape while enabling policy-driven behavior.

## Consequences

Positive:

- Tenant-level capability behavior can be changed without code changes.
- lotus-gateway/UI can remain contract-driven while lotus-core controls rollout semantics.

Trade-offs:

- Misconfigured override JSON could silently drift intent without tests.
  Mitigated by validation + fallback behavior and unit coverage.

## Tests

Added/updated tests:

- `tests/unit/services/query_service/services/test_capabilities_service.py`
  - default behavior
  - global env overrides
  - tenant override application
  - invalid override JSON fallback

