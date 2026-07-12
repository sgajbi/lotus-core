# CR-1328 Microservice Boundary Matrix Refresh

## Objective

Fix GitHub issue #633 by refreshing the microservice boundary matrix so it separates in-process
design boundaries from runtime deployable boundaries.

## Expected Improvement

The matrix now teaches the intended sequence: strengthen packages, use cases, domain policies,
ports, adapters, proof builders, and contract artifacts first; add or expand a runtime boundary
only when scale, deployment cadence, operations ownership, persistence ownership, failure
isolation, security, or SLO evidence proves the in-process boundary is insufficient.

## Changes

1. Added design-before-runtime reading guidance and current links.
2. Added an in-process boundary matrix for every current deployable.
3. Added runtime split rationale criteria for every current deployable.
4. Marked all current deployables as historical/current-state revalidation, not new approval.
5. Added `no split yet` patterns for scheduler, simulation, upload, replay, and proof/evidence
   workflows.
6. Updated README, architecture index, wiki architecture navigation, repository context, and the
   codebase review ledger.

## Compatibility Impact

No route path, request DTO, response DTO, OpenAPI metadata, Kafka topic, event payload, database
schema, repository SQL, metric name, runtime wiring, deployment topology, Dockerfile, package
import path, or public behavior changed.

## No Runtime Split Decision

This is a documentation and governance refresh only. It does not approve any new runtime split or
change the current deployable catalog.

## Validation Evidence

Focused validation was run before commit:

1. `python scripts/runtime_boundary_decision_guard.py`
2. `make architecture-guard`
3. `python scripts/wiki_validation_guard.py`
4. `git diff --check`
