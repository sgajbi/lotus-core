# RFC 044 - lotus-core Policy Visibility Endpoint and Provenance Metadata

- Status: IMPLEMENTED
- Date: 2026-02-24
- Owners: lotus-core Query Service

## Context

lotus-core core snapshot policy governance is now enforced by backend policy configuration.
The next gap is visibility: consumers and operators need an explicit API to inspect
effective policy resolution and provenance for tenant/consumer contexts.

## Decision

1. Add `GET /integration/policy/effective` for policy diagnostics.
2. Include policy provenance metadata in core snapshot response metadata:
   - `policy_version`
   - `policySource`
   - `matched_rule_id`
   - `strict_mode`
3. Keep policy decisioning and provenance in lotus-core backend only.

## Rationale

1. Improves supportability for policy-governed integration behavior.
2. Enables lotus-gateway/UI observability without shifting policy logic to clients.
3. Makes policy rollout behavior deterministic and testable.

## Consequences

Positive:

1. Operators can inspect effective policy context directly from lotus-core.
2. Snapshot behavior is easier to explain and debug.

Trade-offs:

1. Additional API and metadata contract fields to maintain.

## Tests

Added/updated:

1. `tests/unit/services/query_service/services/test_integration_service.py`
2. `tests/integration/services/query_service/test_integration_router_dependency.py`

Coverage includes:

1. effective policy response shape,
2. strict mode and allowed section resolution,
3. policy provenance values in core snapshot metadata.

