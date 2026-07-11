# CR-1528: Query-Control-Plane Generic Simulation Ownership

Date: 2026-07-12
Issues: #715, #465
Status: Implemented locally; complete QCP image closure remains open

## Objective

Move the generic simulation route family into the distribution that owns and serves it, while
replacing query-service implementation imports with layered QCP contracts, application commands
and results, domain records/policy, ports, and SQLAlchemy adapters.

## Finding

QCP served every `/simulation-sessions/*` route but imported its DTO, service, position repository,
instrument repository, simulation repository, unit of work, decimal helpers, and position-effect
policy from the query-service package. The QCP wheel therefore omitted its own implementation and
the clean image failed unless Compose mounted query-service source.

The old service also accepted API DTOs, constructed concrete repositories, retained the SQLAlchemy
session, and returned ORM-backed state. Moving that module unchanged would have corrected a folder
name without correcting dependency direction.

## Implementation

- Moved the unchanged public Pydantic contract to QCP `app/contracts/simulation.py`.
- Added immutable session, change, position-baseline, and instrument domain records.
- Added framework-independent create/change commands and session/change/projection result records.
- Added `SimulationStore`, `SimulationBaselineReader`, and `SimulationUnitOfWork` ports.
- Added QCP SQLAlchemy adapters that preserve current-epoch snapshot reconciliation, deterministic
  position-history fallback, normalized instrument lookup, versioned session mutation, ordered
  changes, and explicit commit/rollback ownership.
- Moved transaction-type quantity effects into QCP domain policy backed by the governed transaction
  registry.
- Converted the router into a request-command and result-response mapper while preserving paths,
  schemas, examples, error codes, and statuses.
- Deleted the now-unused query-service simulation workflow and generic unit-of-work files.
- Moved behavioral tests to QCP ownership and replaced concrete-constructor patching with fake-port
  tests. Added adapter mapping and SQL-shape tests.
- Updated architecture, runtime-provider, test-manifest, supported-feature, and port-catalog guards.

## Compatibility

No route, HTTP method, request field, response field, OpenAPI schema, error code/status, database
table, column, transaction-type effect, baseline selection rule, or downstream contract changed.
The query-service `SimulationRepository` remains temporarily for the query-service Core snapshot
implementation; QCP generic simulation does not import or call it.

## Validation

- QCP unit/integration plus Core snapshot compatibility cohort: `367 passed`.
- Focused application, adapter, router, and guard cohort: `79 passed`.
- Scoped MyPy: `8 source files`, no issues.
- Scoped Ruff and diff checks: passed.
- Full `make architecture-guard`: passed.
- `make openapi-gate api-vocabulary-gate`: passed.
- QCP wheel built and installed; imports of simulation application, contract, and SQL adapter
  passed with no query-service source in the installed closure.

## Same-Pattern And Remaining Closure

QCP still imports four query-service-owned implementation families: analytics inputs/exports,
Core snapshot/integration, operations/support, and quarantined advisory simulation compatibility.
The clean `app.main` image proof and Compose bind-mount removal therefore remain open under #715.
The legacy query-service simulation repository is deleted only when Core snapshot ownership moves,
not before.

Generic simulation remains source-effect projection, not advisory recommendation or suitability.
#709, #710, and #711 retain projection-economics, immutable baseline, tenant, concurrency, and
durable-idempotency improvements that were not silently claimed by this ownership move.

## Documentation Decision

Updated repository context, database ownership catalog, current RFC implementation references,
QCP wiki source, supported-feature evidence, application-port catalog, and review ledger. No API
consumer migration note is required because the public contract is unchanged.
