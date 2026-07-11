# CR-1522: Query-Control-Plane Capability Ownership

Date: 2026-07-11
Issues: #465, #715
Status: Implemented locally; complete QCP package closure remains open

## Objective

Move one QCP-only contract family out of query-service ownership without changing its public API,
policy behavior, database lookup, or runtime topology.

## Findings

- `GET /integration/capabilities` is served only by query control plane, but its DTO, policy, and
  application service lived under `query_service`.
- QCP imported those QS internals despite owning the route, settings, security middleware, OpenAPI,
  and downstream contract.
- A clean QCP image cannot currently import `app.main` because many additional QCP route families
  have the same undeclared QS source dependency. Local Compose masks the defect with a query-service
  source bind mount; #715 records the exact image failure.
- The implementation-backed route catalog contains 76 QCP routes across analytics-input,
  control-plane/policy, snapshot/simulation, and shared operational families versus 30 QS routes
  across operational reads and shared operational endpoints. Route count does not justify merging;
  serving-plane security, workload, and operator-contract isolation remain the current reason to
  keep two deployables.

## Implementation

- Moved capability HTTP models to `query_control_plane_service.app.contracts.capabilities`.
- Moved capability policy and orchestration to QCP `app.application` ownership.
- Moved capability tests to the QCP application test tree and preserved router overrides.
- Added QCP-owned policy settings for policy version, tenant overrides, and database availability.
- Closed four `Any` leaks in QCP settings wrappers.
- Added a structural guard against capability code importing QS internals and a no-return check for
  retired QS paths.

## Compatibility

No route path, query parameter, response field, OpenAPI schema, environment variable, tenant
override format, feature/workflow decision, as-of fallback, database table/query, security policy,
or deployable topology changed.

## Validation

- Full QCP unit/integration cohort: `300 passed`.
- Focused capability/settings/architecture cohort: `50 passed`.
- Installed-source QCP capability imports passed without the repository-root `src` package.
- Scoped MyPy, Ruff lint/format, and strict architecture guard passed.
- Reconciliation onto the post-PR-727 mainline reran focused capability, settings, architecture,
  MyPy, Ruff, OpenAPI, documentation, and diff checks; clean-image proof remains under #715.

## Decision And Follow-Up

Keep QS and QCP as separate serving planes for now. QCP has materially different source-product,
simulation, support, policy, authorization, and operator-contract responsibilities. The current
problem is not the two HTTP processes; it is that QCP-only implementation was filed under QS and
the QCP image relied on bind-mounted QS internals.

Continue moving QCP-only families behind QCP-owned application/contract/port/infrastructure
boundaries. Close #715 only when the clean committed image imports and starts without source mounts.
Revisit runtime merge only if load, security, availability, deployment, and operational evidence
shows that one process is simpler without weakening isolation.
