# Layering and Boundary Rules

This standard defines guardrails for directory organization and dependency boundaries in `lotus-core`.

## Rules

1. Service entrypoints must stay thin.
 - No heavy business logic in `app/main.py`, router modules, or worker bootstraps.
2. Domain logic must be transport-agnostic.
 - Domain code cannot depend on FastAPI, Kafka clients, or SQLAlchemy sessions.
3. Adapter code must not become a second domain layer.
 - Adapters translate IO/protocols and delegate to application/domain logic.
4. API contracts are canonical integration boundaries.
 - No downstream direct DB access contract.
5. Removed ownership domains must not re-enter lotus-core.
 - Risk/performance/concentration/reporting orchestration logic is out of scope.
6. Position-level core metrics must converge on canonical positions resources.
 - Avoid parallel position contracts with overlapping semantics.

## Enforcement Approach

1. Documentation and RFC gate:
 - Architecture and ownership changes require RFC updates.
2. Static checks:
 - Use script-based guard checks for known boundary violations.
 - `make architecture-guard` enforces removed-domain import exclusions and selected direct-import
   boundaries:
   - query-control-plane routers must not import query-service repositories directly,
   - query runtime routers must not import query-control-plane internals,
   - ingestion routers must not import other service implementations directly.
   - API routers must not add database session dependencies, repository construction, external
     client access, file access, or direct SQLAlchemy operations outside the transitional exception
     registry in `docs/standards/api-layer-router-boundary-exceptions.json`.
3. CI conformance:
 - OpenAPI, vocabulary, no-alias, and migration checks remain mandatory.

## Module Size Budget

Tracked Python modules under `src/` have a hard budget of 1,500 physical lines. The blocking
`make quality-source-size-gate` command reads Git's tracked-file inventory so ignored build output
cannot make local and clean-CI results diverge.

Existing modules above the budget are recorded in `quality/module-size-baseline.v1.json` with an
owner, rationale, owning issue, review expiry, and exact current line count. The baseline has zero
headroom:

1. a new module above 1,500 lines fails,
2. growth of a baseline module fails,
3. shrinkage or removal fails until the baseline is ratcheted in the same change, and
4. an expired baseline entry fails.

The baseline is transitional debt authority, not permission to add code to an oversized module.
Issue #462 owns decomposition and removal of the remaining entries.

## Transitional Policy

During RFC 057 rollout:

1. Structural refactors are performed in small PRs with behavior lock tests.
2. Transitional endpoints are removed when approved in RFC 057 decisions.
3. Downstream migrations are tracked in downstream repositories; lotus-core does not retain legacy ownership APIs.
