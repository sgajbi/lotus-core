# Runtime Boundary Decision Standard

Lotus Core must prefer clean in-process modularity before adding or expanding deployable service,
worker, or scheduler boundaries.

## Principle

First create a clear in-process boundary using packages, domain modules, application use cases,
ports, adapters, proof builders, tests, and explicit contracts. Create or expand a separate
deployable only when independent runtime scaling, deployment cadence, operational ownership,
persistence ownership, failure isolation, security boundary, or materially different SLO evidence
proves the package boundary is insufficient.

## Required Records

New deployable service roots, workers, or scheduler processes require:

1. a runtime-boundary decision record based on
   `docs/architecture/templates/runtime-boundary-decision-record-template.md`,
2. an entry in `docs/architecture/runtime-boundary-decision-catalog.json`,
3. proof that in-process boundaries and fake-adapter tests were considered first,
4. explicit compatibility impact for APIs, events, database ownership, metrics, runbooks, and
   downstream consumers.

Refactors that intentionally improve in-process modularity only must include a no-runtime-split
rationale in their CR, RFC, or codebase-review ledger entry. The rationale must state that the
slice does not create a new deployable, database, queue, or operational ownership boundary.

## Existing Deployables

Existing Dockerfile-backed services are cataloged as `current-state-revalidation-required` unless a
specific runtime-boundary decision record has already approved them. This status documents current
truth without inventing retrospective approval.

Future revalidation should either:

1. approve the runtime split with evidence,
2. retain it as current-state with explicit migration constraints,
3. plan consolidation if the runtime boundary lacks scaling, ownership, failure-isolation, or
   security evidence.

Use `runtime-consolidation-planned` only for an existing baseline deployable with a named
`consolidationTargetServiceId` and an implementation-backed decision record. Planned consolidation
does not authorize deleting the current runtime until compatibility, failure, replay, throughput,
operability, image provenance, and rollback evidence passes.

Use `runtime-consolidation-target` only for a new target deployable whose `serviceId` is referenced
by at least one baseline `runtime-consolidation-planned` record. This status records target
implementation and validation without claiming cutover; it must not be used for an unrelated new
runtime split or an existing baseline service.

## Enforcement

`make architecture-guard` runs `scripts/quality/runtime_boundary_decision_guard.py`.

The guard:

1. discovers deployable service roots by `src/services/**/Dockerfile`,
2. requires every deployable root to have a catalog entry,
3. blocks stale catalog entries,
4. prevents new service paths from using `current-state-revalidation-required`,
5. requires decision records and evidence fields,
6. requires this standard, the runtime-boundary template, and the PR checklist item.

## PR Checklist

Any PR that adds a Dockerfile-backed service, worker, scheduler, or deployable boundary must link
the runtime-boundary decision record and catalog entry. If the PR is in-process modularity only,
the PR must point to the no-runtime-split rationale in the CR, RFC, or ledger entry.
