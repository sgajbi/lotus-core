# RFC 038 - lotus-core Integration Capabilities API

## Status
Accepted

## Context
Platform RFCs require backend-driven configurability and explicit capability negotiation for lotus-gateway/lotus-performance/lotus-manage consumers. lotus-core lacked a single discoverable API for feature/workflow capability metadata.

## Decision
Add `GET /integration/capabilities` in query-service.

Inputs:
- `consumer_system` (lotus-gateway, lotus-performance, lotus-manage, UI, UNKNOWN)
- `tenant_id`

Output:
- contract and policy metadata
- supported input modes (`lotus_core_ref`, `inline_bundle`)
- feature capability flags
- workflow capability flags

Configuration source:
- environment-backed flags (for now), designed to evolve into policy-pack/control-plane backed resolution.

## Rationale
1. Keeps feature/workflow control in backend services.
2. Enables lotus-gateway/UI to render from capabilities rather than hardcoded assumptions.
3. Supports lotus-performance/lotus-manage dual-mode strategy (connected and stateless).

## Consequences
### Positive
- Explicit service-level integration contract for capability discovery.
- Cleaner separation of responsibilities between UI/lotus-gateway and domain services.

### Negative
- Requires ongoing governance to prevent uncontrolled feature-flag growth.
