# CR-011 Living Documentation Ownership Drift Review

## Scope

Review living documentation for stale ownership references after the RFC 81 service split.

Reviewed surfaces:

- `docs/Database-Schema-Catalog.md`
- `docs/features/timeseries_generator/04_Operations_Troubleshooting_Guide.md`
- `docs/standards/durability-consistency.md`

This review intentionally excludes historical RFC evidence documents unless they claim
to be current-state architecture references.

## Findings

### 1. Living docs still described pre-split service ownership

Several living documents still attributed control-plane APIs and portfolio aggregation
responsibilities to the pre-RFC-81 service layout.

Examples:

- integration/capabilities/simulation/analytics-input references still pointed at
  `query_service` routers as if those endpoints were part of the core read plane
- portfolio-level aggregation still referenced
  `timeseries_generator_service/app/consumers/portfolio_timeseries_consumer.py`
  even though that runtime no longer exists in the split architecture

### 2. Historical RFC documents should not all be rewritten

Many RFCs and historical evidence notes legitimately reference the package/file layout
that existed when those RFCs were implemented.

Those are records, not always current-state docs.

The right correction target is:

- living standards
- architecture docs
- operational runbooks
- current schema/ownership catalogs

not every historical RFC artifact.

## Action taken

Updated living docs to align with the current split:

- `query_control_plane_service` now owns current references for:
  - support APIs
  - integration contracts
  - analytics-input exports
  - simulation workflows
- `portfolio_aggregation_service` now owns current references for:
  - portfolio-level aggregation
  - portfolio timeseries orchestration
- `timeseries_generator_service` references were narrowed to position-timeseries worker ownership

## Recommendation

1. Keep living docs aligned with current ownership.
2. Preserve historical RFC evidence unless it falsely claims to represent current architecture.
3. Treat documentation drift as a first-class review concern after any service split.

## Sign-off state

Current state: `Hardened`

Reason:

- obvious stale ownership references in living docs were corrected
- historical RFC evidence was intentionally preserved rather than flattened
