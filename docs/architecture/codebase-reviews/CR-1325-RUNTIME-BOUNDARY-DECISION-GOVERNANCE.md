# CR-1325 Runtime Boundary Decision Governance

## Scope

Issue cluster: GitHub issue #630.

This slice adds design-before-runtime-split governance for deployable service, worker, scheduler,
and runtime boundary changes.

## Objective

Prevent new runtime deployables from being introduced on conceptual importance alone. Future
runtime splits must prove that an in-process package/module boundary was designed, tested, and
found insufficient before deployment, scaling, ownership, failure-isolation, persistence, or
security boundaries are added.

## Changes

1. Added `docs/architecture/runtime-boundary-decision-catalog.json` covering all 14 current
   Dockerfile-backed deployables as `current-state-revalidation-required`.
2. Added `docs/architecture/templates/runtime-boundary-decision-record-template.md` with required
   in-process boundary evidence, runtime drivers, compatibility, validation, and catalog update
   sections.
3. Added `docs/standards/runtime-boundary-decision-standard.md`, including no-runtime-split
   rationale requirements for in-process modularity-only refactors.
4. Added `scripts/runtime_boundary_decision_guard.py`, which discovers
   `src/services/**/Dockerfile`, requires catalog entries, blocks stale entries, prevents new
   service paths from using current-state status, and verifies governance files and PR checklist
   coverage.
5. Added guard tests for cataloged baseline services, missing catalog entries, stale entries, new
   current-state services, and missing decision records.
6. Wired `runtime-boundary-decision-guard` into `make architecture-guard`.
7. Updated the PR template with a runtime-boundary decision/no-runtime-split checklist item.

## Behavior And Compatibility

No route path, request DTO, response DTO, OpenAPI metadata, Kafka topic, event payload, database
schema, repository SQL, metric name, runtime wiring, deployment topology, or Dockerfile changed.

Existing deployables are not retroactively approved by this slice. They are cataloged as
current-state and revalidation-required against the existing microservice boundary matrix.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/scripts/test_runtime_boundary_decision_guard.py -q`
2. `python scripts/runtime_boundary_decision_guard.py`
3. `python -m ruff check scripts/runtime_boundary_decision_guard.py tests/unit/scripts/test_runtime_boundary_decision_guard.py --ignore E501,I001`
4. `python -m ruff format --check scripts/runtime_boundary_decision_guard.py tests/unit/scripts/test_runtime_boundary_decision_guard.py`

Aggregate validation before commit:

1. `make architecture-guard`
2. `python scripts/wiki_validation_guard.py`
3. `git diff --check`

All listed commands passed locally before commit.

## Documentation, Wiki, Context, And Skill Decision

Updated repo-local standards, architecture overview, codebase review ledger, PR template, and repo
context.

No wiki update is required because this slice changes internal engineering governance and PR/docs
checks without changing operator-facing commands, public API behavior, supported features, or
published wiki truth.

No platform skill source change is required in this slice because the repo-local standard and guard
are the actionable implementation for lotus-core runtime-boundary hygiene. The existing backend
delivery guidance already requires preserving behavior and documenting intentional architecture
changes.

## Remaining Work

GitHub issue #630 is locally fixed for decision-record templates, no-runtime-split rationale
requirements, current deployable cataloging, CI/docs guard coverage, and PR checklist visibility
pending PR CI/QA and issue closure.

Future runtime-boundary revalidation should turn current-state entries into explicit approve,
retain-with-constraints, or consolidate decisions.
