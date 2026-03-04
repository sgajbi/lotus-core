# RFC 043 - lotus-core Core Snapshot Contract Hardening (Freshness, Lineage, Section Governance)

- Status: IMPLEMENTED
- Date: 2026-02-24
- Owners: lotus-core Query Service

## Context

`POST /integration/portfolios/{portfolio_id}/core-snapshot` is the canonical lotus-core boundary for
lotus-performance, lotus-manage, and lotus-gateway composition. The current response shape is stable but lacks explicit:

1. freshness/provenance metadata,
2. section governance metadata,
3. tenant/consumer policy controls for allowed sections.

## Decision

Harden the existing contract while preserving endpoint semantics:

1. Add `metadata` in response with:
   - `generated_at`
   - `source_as_of_date`
   - `freshness_status`
   - `lineage_refs`
   - `sectionGovernance`
2. Add backend policy controls via `LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON`:
   - consumer-specific allowed section lists
   - tenant override allowed section lists
   - strict mode for disallowed section requests (`403`)
3. Keep policy enforcement in lotus-core backend; consumers do not implement section entitlement logic.

## Rationale

1. Strengthens integration readiness for lotus-gateway/lotus-performance/lotus-manage and support workflows.
2. Improves productized behavior through backend-driven policy control.
3. Preserves lotus-core service boundary as canonical snapshot owner.

## Consequences

Positive:

1. Consumers get explicit freshness/provenance semantics.
2. Section control behavior is deterministic and testable.
3. Contract drift risk is reduced by invariants in lotus-core test suites.

Trade-offs:

1. Slightly larger payload and additional policy configuration complexity.

## Tests

Added/updated:

1. `tests/unit/services/query_service/services/test_integration_service.py`
2. `tests/integration/services/query_service/test_integration_router_dependency.py`

Coverage includes:

1. metadata shape and default governance behavior,
2. policy filtering behavior,
3. strict mode rejection on disallowed section requests,
4. tenant override behavior.

