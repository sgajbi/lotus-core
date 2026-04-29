# ADR 003 - Integration Capabilities API in lotus-core Query Service

- Status: Accepted
- Date: 2026-02-23

## Context

lotus-core must expose backend-driven capability metadata to support:
1. lotus-gateway/UI feature visibility and workflow control.
2. lotus-performance/lotus-manage integration negotiation and dual input mode support.
3. Architectural rule that policy complexity remains in backend services.
4. RFC-0108 ecosystem-wide operational posture discovery for `lotus-workbench`,
   `lotus-advise`, `lotus-risk`, and `lotus-report` without treating portfolio readiness as
   an implicit side effect of route availability.

## Decision

Implement `GET /integration/capabilities` in lotus-core query-service with:
1. consumer-aware capability resolution (`consumer_system`)
2. tenant-aware context (`tenant_id`)
3. policy/capability metadata response including supported input modes.
4. explicit publication of `core.observability.portfolio_supportability`, backed by
   `GET /support/portfolios/{portfolio_id}/readiness` and the
   `lotus_core_portfolio_supportability_total` Prometheus counter.

Initial implementation resolves feature flags from environment variables. This is an interim step until centralized policy-pack configuration is introduced.

## Consequences

### Positive
1. lotus-gateway/UI can consume explicit backend capability contracts.
2. Integration behavior is discoverable and testable.
3. Aligns lotus-core with platform RFCs for backend configurability.
4. Gateway, Workbench, and downstream apps can compose portfolio supportability uniformly across
   Lotus instead of inferring health from portfolio data counts or route presence.

### Negative
1. Environment-driven flag model is not yet centralized.
2. Requires future migration to shared policy/config service for multi-tenant scale.

## Links

1. `docs/RFCs/RFC 038 - lotus-core Integration Capabilities API.md`
2. `src/services/query_control_plane_service/app/routers/capabilities.py`
